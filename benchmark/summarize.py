"""Tổng hợp kết quả thực nghiệm thành bảng Markdown (và biểu đồ nếu có matplotlib).

Chạy từ thư mục ``Source/``::

    python benchmark/summarize.py benchmark/results/<thời điểm>

``run.py`` tự gọi module này sau khi chạy xong. Không lọc bỏ lần chạy lỗi:
mọi TIMEOUT/ERROR/STUCK/INCONSISTENT đều xuất hiện trong bảng và mục "Thất bại".
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

METRICS = ["num_primary_variables", "num_auxiliary_variables", "num_clauses", "sat_calls",
           "decisions", "propagations", "backtracks", "deduction_steps"]
HEADERS = {"num_primary_variables": "Primary vars", "num_auxiliary_variables": "Aux vars",
           "num_clauses": "Clauses", "sat_calls": "SAT calls", "decisions": "Decisions",
           "propagations": "Propagations", "backtracks": "Backtracks", "deduction_steps": "Steps"}
# Màu cố định theo kích thước bảng (theo thứ tự, không xoay vòng).
SIZE_COLORS = {3: "#2a78d6", 4: "#eb6834", 5: "#1baf7a"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(value: str | None) -> float | None:
    return None if value in (None, "") else float(value)


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "–"
    return f"{value:,.{digits}f}" if digits else f"{value:,.0f}"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _metric_cell(values: list[float | None]) -> str:
    present = [value for value in values if value is not None]
    if not present:
        return "–"
    if len(set(present)) == 1:
        return _fmt(present[0])
    return f"{_fmt(min(present))}–{_fmt(max(present))}"  # khác nhau giữa các lần lặp


def write_summary(results_directory: Path) -> Path:
    """Đọc các file kết quả trong ``results_directory`` và ghi ``summary.md``."""
    results_directory = Path(results_directory)
    records = _read_csv(results_directory / "results.csv")
    checks = {row["puzzle_id"]: row for row in _read_csv(results_directory / "puzzle_checks.csv")}
    log_path = results_directory / "run_log.jsonl"
    logs = {}
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                logs[entry["run_id"]] = entry
    environment_path = results_directory / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8")) if environment_path.is_file() else {}

    by_puzzle: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in records:
        by_puzzle[record["puzzle_id"]].append(record)

    lines = ["# Kết quả thực nghiệm (mục 4.5)", ""]
    if environment:
        lines += ["## Cấu hình chạy", ""]
        for key in ("started_at", "python_version", "platform", "processor", "cpu_count", "solver_config",
                    "repeats", "timeout_ms", "process_model", "runtime_definition"):
            lines.append(f"- `{key}`: {environment.get(key)}")
        lines.append("")

    lines += ["## Bảng theo puzzle", "",
              "Bộ đếm lấy theo từng lần chạy; nếu khác nhau giữa các lần lặp thì ghi `min–max`. "
              "Runtime là trung vị (min–max) qua các lần lặp, đơn vị ms. Kỳ vọng lấy từ oracle độc lập.", ""]
    headers = ["Puzzle", "Size", "Runs", "Result", "Expected"] + [HEADERS[m] for m in METRICS] + ["Runtime ms"]
    rows = []
    for puzzle_id, runs in by_puzzle.items():
        results = sorted({run["result"] for run in runs})
        runtimes = [_number(run["runtime_ms"]) for run in runs]
        runtimes = [value for value in runtimes if value is not None]
        expected = checks.get(puzzle_id, {}).get("oracle_deduction_state") or "–"
        runtime_text = "–"
        if runtimes:
            runtime_text = f"{statistics.median(runtimes):,.1f} ({min(runtimes):,.1f}–{max(runtimes):,.1f})"
        rows.append([puzzle_id, f"{runs[0]['grid_size']}×{runs[0]['grid_size']}" if runs[0]["grid_size"] else "–",
                     str(len(runs)), "/".join(results), expected]
                    + [_metric_cell([_number(run[m]) for run in runs]) for m in METRICS] + [runtime_text])
    lines += _table(headers, rows) + [""]

    lines += ["## Trung bình theo kích thước (chỉ các lần SOLVED)", ""]
    size_rows = []
    by_size: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in records:
        by_size[record["grid_size"] or "?"].append(record)
    for grid_size in sorted(by_size, key=lambda size: (size == "?", size)):
        runs = by_size[grid_size]
        solved = [run for run in runs if run["result"] == "SOLVED"]
        averages = []
        for metric in METRICS + ["runtime_ms"]:
            values = [_number(run[metric]) for run in solved if _number(run[metric]) is not None]
            averages.append(_fmt(statistics.mean(values), 1) if values else "–")
        size_rows.append([f"{grid_size}×{grid_size}", str(len({run['puzzle_id'] for run in runs})),
                          f"{len(solved)}/{len(runs)}"] + averages)
    lines += _table(["Size", "Puzzles", "SOLVED runs"] + [HEADERS[m] for m in METRICS] + ["Runtime ms"],
                    size_rows) + [""]

    lines += ["## Thất bại, timeout và trạng thái khác SOLVED", "",
              "Không loại bỏ khỏi kết quả (theo yêu cầu đề). `Khớp kỳ vọng` so với oracle độc lập.", ""]
    failure_rows = []
    for record in records:
        if record["result"] == "SOLVED":
            continue
        log_entry = logs.get(record["run_id"], {})
        expected = checks.get(record["puzzle_id"], {}).get("oracle_deduction_state") or "–"
        message = (log_entry.get("error_message") or "").replace("|", "\\|")
        partial = "có" if log_entry.get("partial_metrics") else "không"
        failure_rows.append([record["run_id"], record["result"], expected,
                             "có" if expected == record["result"] else "không", partial, message or "–"])
    lines += (_table(["Run", "Result", "Oracle", "Khớp kỳ vọng", "Số liệu một phần", "Ghi chú"], failure_rows)
              if failure_rows else ["Không có."]) + [""]

    if checks:
        lines += ["## Kiểm tra uniqueness (toàn bộ clue)", ""]
        check_rows = [[row["puzzle_id"], row["uniqueness"] or "–", row["oracle_model_count"] or "–",
                       row["uniqueness_sat_calls"] or "–", row["uniqueness_decisions"] or "–",
                       _fmt(_number(row["uniqueness_runtime_ms"]), 2) if row["uniqueness_runtime_ms"] else "–",
                       (row["note"] or "–").replace("|", "\\|")]
                      for row in checks.values()]
        lines += _table(["Puzzle", "check_uniqueness", "Oracle models (tối đa 2)", "SAT calls", "Decisions",
                         "Runtime ms", "Ghi chú"], check_rows) + [""]

    chart_names = _write_charts(results_directory, by_puzzle)
    if chart_names:
        lines += ["## Biểu đồ", ""] + [f"![{name}]({name})" for name in chart_names] + [""]

    summary_path = results_directory / "summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary_path


def _write_charts(results_directory: Path, by_puzzle: dict[str, list[dict[str, str]]]) -> list[str]:
    """Vẽ biểu đồ cột theo puzzle (màu theo kích thước). Bỏ qua nếu thiếu matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError:
        return []
    puzzles = []
    for puzzle_id, runs in by_puzzle.items():
        grid_size = int(runs[0]["grid_size"]) if runs[0]["grid_size"] else None
        complete = [run for run in runs if run["result"] in ("SOLVED", "STUCK", "INCONSISTENT")]
        if not complete or grid_size is None:
            continue
        puzzles.append((puzzle_id, grid_size, complete))
    if not puzzles:
        return []
    charts = [("runtime_ms", "Runtime (ms, trung vị, thang log)", True, "chart_runtime.png"),
              ("sat_calls", "Số SAT calls mỗi lần chạy", False, "chart_sat_calls.png"),
              ("num_clauses", "Số clause của KB công khai cuối", False, "chart_clauses.png")]
    names = []
    for metric, title, log_scale, file_name in charts:
        figure, axis = plt.subplots(figsize=(10, 4.2), dpi=150)
        labels, values, colors = [], [], []
        for puzzle_id, grid_size, runs in puzzles:
            metric_values = [float(run[metric]) for run in runs if run[metric] != ""]
            if not metric_values:
                continue
            labels.append(puzzle_id.replace("puzzle_", "").replace("fixture_", "fx_"))
            values.append(statistics.median(metric_values))
            colors.append(SIZE_COLORS.get(grid_size, "#6250d6"))
        axis.bar(range(len(values)), values, color=colors, width=0.7, edgecolor="#fcfcfb", linewidth=2)
        axis.set_xticks(range(len(values)), labels, rotation=45, ha="right", fontsize=8, color="#52514e")
        axis.set_title(title, loc="left", fontsize=11, color="#0b0b0b")
        if log_scale:
            axis.set_yscale("log")
        axis.grid(axis="y", color="#e6e5e0", linewidth=0.8)
        axis.set_axisbelow(True)
        for side in ("top", "right", "left"):
            axis.spines[side].set_visible(False)
        axis.spines["bottom"].set_color("#c3c2b7")
        axis.tick_params(axis="y", colors="#52514e", labelsize=8, length=0)
        sizes = sorted({grid_size for _, grid_size, _ in puzzles})
        axis.legend(handles=[Patch(color=SIZE_COLORS.get(size, "#6250d6"), label=f"{size}×{size}") for size in sizes],
                    frameon=False, fontsize=8, loc="upper left")
        figure.tight_layout()
        figure.savefig(results_directory / file_name)
        plt.close(figure)
        names.append(file_name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_directory", type=Path)
    args = parser.parse_args()
    print(write_summary(args.results_directory))
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
