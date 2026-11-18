"""Chạy thực nghiệm headless cho mục 4.5 của đề Project 2.

Chạy từ thư mục ``Source/``::

    python benchmark/run.py                       # bộ puzzle mặc định, 3 lần lặp, timeout 60 s
    python benchmark/run.py --repeats 5 --timeout-ms 120000
    python benchmark/run.py --puzzles puzzles/puzzle_4x4_001.json --repeats 1

Mỗi lần chạy (một puzzle × một lần lặp) diễn ra trong một worker process có
thể dừng được (TEAM_CONVENTIONS mục 10). Worker chỉ dùng API công khai của
nhóm: ``models.load_puzzle``, ``GameEngine``, ``agent.next_move`` và
``encoder.encode``; agent chỉ nhận ``PublicState``.

Kết quả ghi vào ``benchmark/results/<thời điểm>/``:

- ``results.csv``: một dòng mỗi lần chạy, đúng header ở mục 10;
- ``traces/<run_id>.jsonl``: trace JSON Lines của các bước ACCEPTED;
- ``run_log.jsonl``: chi tiết từng lần chạy (lỗi, số liệu một phần, số query theo mục đích);
- ``puzzle_checks.csv``: kết quả ``check_uniqueness`` và kiểm tra đối chứng bằng oracle;
- ``environment.json``: cấu hình máy, Python, timeout và solver_config;
- ``summary.md`` (+ biểu đồ PNG nếu có matplotlib): sinh bởi ``summarize.py``.
"""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import os
import platform
import queue as queue_module
import sys
import traceback
from collections import Counter
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any

SOURCE_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

CSV_FIELDS = ["puzzle_id", "run_id", "grid_size", "solver_config", "seed", "result",
              "num_primary_variables", "num_auxiliary_variables", "num_clauses", "sat_calls",
              "decisions", "propagations", "backtracks", "deduction_steps", "runtime_ms"]
CHECK_FIELDS = ["puzzle_id", "grid_size", "uniqueness", "uniqueness_sat_calls", "uniqueness_decisions",
                "uniqueness_propagations", "uniqueness_backtracks", "uniqueness_runtime_ms",
                "oracle_model_count", "oracle_deduction_state", "oracle_deduction_steps", "note"]
DEFAULT_PUZZLE_GLOBS = ("puzzles/*.json", "benchmark/stress/*.json", "benchmark/fixtures/*.json")
DEFAULT_REPEATS = 3
BENCHMARK_TIMEOUT_MS = 60_000.0
DEFAULT_SOLVER_CONFIG = "dpll_default"
TERMINAL_STATES = ("SOLVED", "STUCK", "INCONSISTENT")


# --------------------------------------------------------------------------- helpers


def field_value(record: Any, name: str) -> Any:
    """Đọc field từ dataclass hoặc dict (giống ``_field`` của engine)."""
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


def to_jsonable(value: Any) -> Any:
    """Chuyển dataclass/Enum/dict key số sang dữ liệu JSON chuẩn."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(to_jsonable(key)): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, float) and value != value:  # NaN không hợp lệ theo quy ước
        return None
    return value


def summarize_queries(query_log: list[dict[str, Any]]) -> dict[str, int]:
    """Cộng dồn bộ đếm solver từ nhật ký query của một lần chạy."""
    total_stats = {"sat_calls": len(query_log), "decisions": 0, "propagations": 0, "backtracks": 0}
    for query in query_log:
        for name in ("decisions", "propagations", "backtracks"):
            total_stats[name] += int(query["stats"][name])
    return total_stats


class ActiveTimer:
    """Đồng hồ monotonic có thể tạm dừng (loại trừ phần đo đếm CNF của runner)."""

    def __init__(self) -> None:
        self.elapsed_ms = 0.0
        self._started_at: float | None = None

    def start(self) -> None:
        self._started_at = perf_counter()

    def stop(self) -> None:
        if self._started_at is not None:
            self.elapsed_ms += (perf_counter() - self._started_at) * 1000
            self._started_at = None


# --------------------------------------------------------------------------- worker side


def _encode_counts(public_state: Any) -> dict[str, int]:
    from griductive.encoder import encode
    encoded_kb = encode(public_state)
    return {"num_primary_variables": int(field_value(encoded_kb, "num_primary_variables")),
            "num_auxiliary_variables": int(field_value(encoded_kb, "num_auxiliary_variables")),
            "num_clauses": int(field_value(encoded_kb, "num_clauses"))}


def deduction_worker(puzzle_path: str, channel: Any) -> None:
    """Chạy vòng suy luận headless cho một puzzle và gửi tiến độ qua ``channel``.

    Message: ``loaded``, ``progress`` (sau mỗi next_move/submit_verdict, mang
    bộ đếm và trace mới), rồi ``done`` hoặc ``error``. Phần đo đếm CNF cho
    báo cáo nằm ngoài đồng hồ runtime.
    """
    phase = "import"
    query_log: list[dict[str, Any]] = []
    trace_entries: list[dict[str, Any]] = []
    cnf_counts: dict[str, int] | None = None
    timer = ActiveTimer()

    def progress(new_trace_entry: dict[str, Any] | None = None) -> None:
        channel.put({"type": "progress", "counters": summarize_queries(query_log),
                     "cnf_counts": cnf_counts, "deduction_steps": len(trace_entries),
                     "trace_entry": new_trace_entry, "runtime_ms": timer.elapsed_ms})

    try:
        from griductive import models
        from griductive.agent import next_move
        from griductive.engine import GameEngine

        phase = "load"
        puzzle = models.load_puzzle(Path(puzzle_path))
        engine = GameEngine(puzzle)
        public_state = engine.get_public_state()
        grid_size = int(field_value(public_state, "grid_size"))
        channel.put({"type": "loaded", "puzzle_id": field_value(public_state, "puzzle_id"),
                     "grid_size": grid_size})

        phase = "encode"
        cnf_counts = _encode_counts(public_state)
        phase = "deduction"
        terminal_state = None
        max_iterations = grid_size * grid_size + 1
        for _ in range(max_iterations):
            timer.start()
            move_result = next_move(public_state)
            timer.stop()
            move_queries = [to_jsonable(query) for query in field_value(move_result, "sat_queries")]
            query_log.extend(move_queries)
            state = to_jsonable(field_value(move_result, "state"))
            if state != "MOVE_AVAILABLE":
                progress()
                terminal_state = state
                break
            cell_id = field_value(move_result, "cell_id")
            verdict = field_value(move_result, "verdict")
            revision_before = int(field_value(public_state, "revision"))
            active_clue_ids = sorted(field_value(clue, "clue_id")
                                     for clue in field_value(public_state, "revealed_clues"))

            timer.start()
            verdict_result = engine.submit_verdict(cell_id, verdict)
            timer.stop()
            verdict_queries = [to_jsonable(query) for query in field_value(verdict_result, "sat_queries")]
            query_log.extend(verdict_queries)
            result = to_jsonable(field_value(verdict_result, "result"))
            if result != "ACCEPTED":
                progress()
                raise RuntimeError(f"agent proposed {cell_id}={to_jsonable(verdict)} "
                                   f"but engine returned {result}")
            public_state = field_value(verdict_result, "public_state")
            trace_entry = {
                "puzzle_id": field_value(public_state, "puzzle_id"),
                "step": len(trace_entries) + 1,
                "revision_before": revision_before,
                "active_clue_ids": active_clue_ids,
                "cell_id": cell_id,
                "verdict": to_jsonable(field_value(verdict_result, "submitted_status")),
                "sat_queries": move_queries + verdict_queries,
                "newly_revealed_clue": to_jsonable(field_value(verdict_result, "newly_revealed_clue")),
            }
            trace_entries.append(trace_entry)
            phase = "encode"
            cnf_counts = _encode_counts(public_state)
            phase = "deduction"
            progress(trace_entry)
        else:
            raise RuntimeError(f"no terminal state after {max_iterations} iterations")

        channel.put({"type": "done", "result": terminal_state, "counters": summarize_queries(query_log),
                     "cnf_counts": cnf_counts, "deduction_steps": len(trace_entries),
                     "runtime_ms": timer.elapsed_ms,
                     "query_purposes": dict(Counter(query["purpose"] for query in query_log))})
    except BaseException as exc:  # noqa: BLE001 - mọi lỗi đều phải được ghi thành ERROR
        timer.stop()
        started = phase not in ("import", "load")
        # Lỗi trước khi bắt đầu suy luận: chưa đo gì nên để trống, không ghi 0.
        channel.put({"type": "error", "phase": phase, "message": f"{type(exc).__name__}: {exc}",
                     "traceback": traceback.format_exc(),
                     "counters": summarize_queries(query_log) if started else None,
                     "cnf_counts": cnf_counts, "deduction_steps": len(trace_entries) if started else None,
                     "runtime_ms": timer.elapsed_ms if started else None})


def uniqueness_worker(puzzle_path: str, channel: Any) -> None:
    """Gọi ``check_uniqueness`` (luồng riêng, được nhận toàn bộ clue)."""
    try:
        from griductive import models
        from griductive.uniqueness import check_uniqueness
        uniqueness_result = check_uniqueness(models.load_puzzle(Path(puzzle_path)))
        channel.put({"type": "done", "result": to_jsonable(uniqueness_result)})
    except BaseException as exc:  # noqa: BLE001
        channel.put({"type": "error", "message": f"{type(exc).__name__}: {exc}",
                     "traceback": traceback.format_exc()})


# --------------------------------------------------------------------------- parent side


def run_in_worker(target: Any, puzzle_path: Path, timeout_ms: float | None,
                  on_message: Any = None) -> tuple[str, dict[str, Any] | None, float]:
    """Chạy ``target`` trong process riêng, có giám sát timeout.

    Trả ``(outcome, last_message, wall_ms)``; outcome là ``done``, ``error``,
    ``timeout`` hoặc ``crash``. ``on_message`` nhận mọi message trung gian.
    """
    context = multiprocessing.get_context("spawn")
    channel = context.Queue()
    process = context.Process(target=target, args=(str(puzzle_path), channel), daemon=True)
    process.start()
    # Đồng hồ timeout bắt đầu khi worker báo "loaded" (đã import + load puzzle);
    # worker không gửi "loaded" thì tính từ lúc khởi động. Giai đoạn khởi động
    # có giới hạn riêng để không treo vô hạn.
    launched_at = perf_counter()
    started_at = launched_at if target is not deduction_worker else None
    startup_limit_ms = 120_000.0
    last_message: dict[str, Any] | None = None
    try:
        while True:
            now = perf_counter()
            if started_at is None and (now - launched_at) * 1000 >= startup_limit_ms:
                return "timeout", last_message, (now - launched_at) * 1000
            if timeout_ms is not None and started_at is not None and (now - started_at) * 1000 >= timeout_ms:
                return "timeout", last_message, (now - started_at) * 1000
            try:
                message = channel.get(timeout=0.05)
            except queue_module.Empty:
                if process.is_alive():
                    continue
                try:
                    message = channel.get(timeout=0.5)
                except queue_module.Empty:
                    return "crash", last_message, (perf_counter() - launched_at) * 1000
            if message["type"] == "loaded" and started_at is None:
                started_at = perf_counter()
            if on_message is not None:
                on_message(message)
            if message["type"] in ("done", "error"):
                return message["type"], message, (perf_counter() - (started_at or launched_at)) * 1000
            last_message = message
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)
        channel.close()


def read_puzzle_header(puzzle_path: Path) -> tuple[str, int | None]:
    """Đọc puzzle_id/grid_size thô để vẫn ghi được dòng ERROR khi load thất bại."""
    try:
        data = json.loads(puzzle_path.read_text(encoding="utf-8"))
        grid_size = data.get("grid_size")
        return str(data.get("puzzle_id") or puzzle_path.stem), grid_size if isinstance(grid_size, int) else None
    except (OSError, ValueError):
        return puzzle_path.stem, None


def run_one(puzzle_path: Path, run_id: str, solver_config: str, timeout_ms: float | None,
            trace_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Chạy một lần và trả ``(experiment_record, log_entry)``."""
    puzzle_id, grid_size = read_puzzle_header(puzzle_path)
    trace_entries: list[dict[str, Any]] = []

    def on_message(message: dict[str, Any]) -> None:
        if message.get("trace_entry"):
            trace_entries.append(message["trace_entry"])

    outcome, message, wall_ms = run_in_worker(deduction_worker, puzzle_path, timeout_ms, on_message)
    message = message or {}
    counters = message.get("counters")
    cnf_counts = message.get("cnf_counts") or {}
    if outcome == "done":
        result, runtime_ms, partial = message["result"], message["runtime_ms"], False
    elif outcome == "timeout":
        result, runtime_ms, partial = "TIMEOUT", wall_ms, True
    else:
        result, partial = "ERROR", True
        runtime_ms = message.get("runtime_ms", wall_ms) if outcome == "error" else wall_ms
    if result not in TERMINAL_STATES + ("TIMEOUT", "ERROR"):
        result, partial = "ERROR", True

    experiment_record = {
        "puzzle_id": puzzle_id, "run_id": run_id, "grid_size": grid_size, "solver_config": solver_config,
        "seed": None, "result": result,
        "num_primary_variables": cnf_counts.get("num_primary_variables"),
        "num_auxiliary_variables": cnf_counts.get("num_auxiliary_variables"),
        "num_clauses": cnf_counts.get("num_clauses"),
        "sat_calls": counters["sat_calls"] if counters else None,
        "decisions": counters["decisions"] if counters else None,
        "propagations": counters["propagations"] if counters else None,
        "backtracks": counters["backtracks"] if counters else None,
        "deduction_steps": message.get("deduction_steps") if counters else None,
        "runtime_ms": None if runtime_ms is None else round(float(runtime_ms), 3),
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in trace_entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log_entry = {
        "run_id": run_id, "puzzle_id": puzzle_id, "puzzle_path": puzzle_path.relative_to(SOURCE_DIRECTORY).as_posix()
        if puzzle_path.is_relative_to(SOURCE_DIRECTORY) else str(puzzle_path),
        "outcome": outcome, "result": result, "partial_metrics": partial,
        "error_phase": message.get("phase") if outcome == "error" else None,
        "error_message": message.get("message") if outcome == "error" else
        ("worker exited without result" if outcome == "crash" else None),
        "traceback": message.get("traceback") if outcome == "error" else None,
        "query_purposes": message.get("query_purposes"),
        "timeout_ms": timeout_ms,
        "trace_file": trace_path.name,
    }
    return experiment_record, log_entry


def check_puzzle(puzzle_path: Path, timeout_ms: float | None) -> dict[str, Any]:
    """Kiểm tra uniqueness bằng module của nhóm + đối chứng bằng oracle độc lập."""
    from benchmark import oracle
    puzzle_id, grid_size = read_puzzle_header(puzzle_path)
    row: dict[str, Any] = {name: None for name in CHECK_FIELDS}
    row.update({"puzzle_id": puzzle_id, "grid_size": grid_size})
    notes = []
    outcome, message, _ = run_in_worker(uniqueness_worker, puzzle_path, timeout_ms)
    if outcome == "done":
        result = message["result"]
        row["uniqueness"] = result["classification"]
        for name in ("sat_calls", "decisions", "propagations", "backtracks", "runtime_ms"):
            row[f"uniqueness_{name}"] = result["stats"][name]
    else:
        row["uniqueness"] = "TIMEOUT" if outcome == "timeout" else "ERROR"
        if message and message.get("message"):
            notes.append(message["message"])
    try:
        data = json.loads(puzzle_path.read_text(encoding="utf-8"))
        clues = [card["clue"] for card in data["cards"]]
        row["oracle_model_count"] = oracle.count_models(clues, data["grid_size"], limit=2)
        simulation = oracle.simulate_deduction(data)
        row["oracle_deduction_state"] = simulation["state"]
        row["oracle_deduction_steps"] = simulation["steps"]
        expected = {0: "UNSAT", 1: "UNIQUE"}.get(row["oracle_model_count"], "MULTIPLE")
        if row["uniqueness"] in ("UNIQUE", "MULTIPLE", "UNSAT") and row["uniqueness"] != expected:
            notes.append(f"MISMATCH: oracle says {expected}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"oracle failed: {type(exc).__name__}: {exc}")
    row["note"] = "; ".join(notes) or None
    return row


def write_csv(path: Path, field_names: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: "" if row.get(name) is None else row[name] for name in field_names})


def collect_puzzles(arguments: list[str] | None) -> list[Path]:
    patterns = arguments or list(DEFAULT_PUZZLE_GLOBS)
    paths: list[Path] = []
    for pattern in patterns:
        candidate = Path(pattern)
        if not candidate.is_absolute():
            candidate = SOURCE_DIRECTORY / candidate
        matches = sorted(candidate.parent.glob(candidate.name)) if any(ch in pattern for ch in "*?[") else [candidate]
        paths.extend(path for path in matches if path.is_file())
    unique_paths = list(dict.fromkeys(path.resolve() for path in paths))
    if not unique_paths:
        raise SystemExit(f"Không tìm thấy puzzle nào từ: {patterns}")
    return unique_paths


def describe_environment(args: argparse.Namespace, timeout_ms: float | None) -> dict[str, Any]:
    return {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "solver_config": args.solver_config,
        "repeats": args.repeats,
        "timeout_ms": timeout_ms,
        "process_model": "one spawned worker process per run",
        "runtime_definition": "monotonic perf_counter; next_move + submit_verdict only; excludes load, "
                              "validation, uniqueness, CNF counting and file output",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--puzzles", nargs="*", help="File/glob puzzle (tính từ Source/). Mặc định: "
                        + ", ".join(DEFAULT_PUZZLE_GLOBS))
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS, help="Số lần lặp mỗi puzzle")
    parser.add_argument("--timeout-ms", type=float, default=BENCHMARK_TIMEOUT_MS,
                        help="Giới hạn cho mỗi lần chạy, ms (<= 0 nghĩa là không giới hạn)")
    parser.add_argument("--solver-config", default=DEFAULT_SOLVER_CONFIG,
                        help="Tên cấu hình solver ghi vào CSV (mô tả trong báo cáo)")
    parser.add_argument("--output-dir", type=Path, help="Thư mục kết quả (mặc định benchmark/results/<thời điểm>)")
    parser.add_argument("--skip-uniqueness", action="store_true", help="Bỏ qua puzzle_checks.csv")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats phải >= 1")
    timeout_ms = args.timeout_ms if args.timeout_ms and args.timeout_ms > 0 else None

    puzzle_paths = collect_puzzles(args.puzzles)
    output_directory = args.output_dir or (SOURCE_DIRECTORY / "benchmark" / "results"
                                           / datetime.now().strftime("%Y%m%d-%H%M%S"))
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "environment.json").write_text(
        json.dumps(describe_environment(args, timeout_ms), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    records: list[dict[str, Any]] = []
    log_entries: list[dict[str, Any]] = []
    total = len(puzzle_paths) * args.repeats
    print(f"{len(puzzle_paths)} puzzle × {args.repeats} lần = {total} lần chạy; "
          f"timeout={timeout_ms} ms; kết quả -> {output_directory}", flush=True)
    counter = 0
    for repeat in range(1, args.repeats + 1):
        for puzzle_path in puzzle_paths:
            counter += 1
            puzzle_id, _ = read_puzzle_header(puzzle_path)
            run_id = f"{args.solver_config}__{puzzle_id}__r{repeat:02d}"
            experiment_record, log_entry = run_one(puzzle_path, run_id, args.solver_config, timeout_ms,
                                                   output_directory / "traces" / f"{run_id}.jsonl")
            records.append(experiment_record)
            log_entries.append(log_entry)
            extra = f"  ({log_entry['error_message']})" if log_entry["error_message"] else ""
            runtime_text = ("–" if experiment_record["runtime_ms"] is None
                            else f"{experiment_record['runtime_ms']:.1f} ms")
            print(f"[{counter:3d}/{total}] {run_id:45s} {experiment_record['result']:12s} "
                  f"steps={experiment_record['deduction_steps']} sat_calls={experiment_record['sat_calls']} "
                  f"runtime={runtime_text}{extra}", flush=True)

    write_csv(output_directory / "results.csv", CSV_FIELDS, records)
    with (output_directory / "run_log.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for entry in log_entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if not args.skip_uniqueness:
        print("Kiểm tra uniqueness ...", flush=True)
        check_rows = [check_puzzle(path, timeout_ms) for path in puzzle_paths]
        write_csv(output_directory / "puzzle_checks.csv", CHECK_FIELDS, check_rows)

    from benchmark.summarize import write_summary
    summary_path = write_summary(output_directory)
    print(f"Xong. Bảng tổng hợp: {summary_path}")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
