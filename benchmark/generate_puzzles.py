"""Sinh và kiểm tra bộ puzzle dùng cho thực nghiệm mục 4.5.

Chạy từ thư mục ``Source/``::

    python benchmark/generate_puzzles.py           # sinh lại toàn bộ (tất định theo seed)
    python benchmark/generate_puzzles.py --check   # chỉ kiểm tra các file đã có

Mọi puzzle theo schema TEAM_CONVENTIONS 1.0.0. Việc kiểm tra dùng
``benchmark/oracle.py`` (bộ giải đối chứng độc lập), không cần module của nhóm.

Loại puzzle:

- ``standard``: nghiệm duy nhất và vòng suy luận no-guess mở được hết (SOLVED).
- ``stuck``: toàn bộ clue có nghiệm duy nhất nhưng suy luận từ thông tin công khai bị STUCK.
- ``ambiguous``: toàn bộ clue có nhiều nghiệm, suy luận bị STUCK.
- ``inconsistent``: clue mở sau gây mâu thuẫn, kỳ vọng INCONSISTENT.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from random import Random
from typing import Any

SOURCE_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from benchmark import oracle  # noqa: E402

SCHEMA_VERSION = "1.0.0"
DEFAULT_RANDOM_SEED = 42
PUZZLE_DIRECTORY = SOURCE_DIRECTORY / "puzzles"
FIXTURE_DIRECTORY = SOURCE_DIRECTORY / "benchmark" / "fixtures"
# 5×5 để riêng: GUI nạp mọi file trong puzzles/, mà SUPPORTED_GRID_SIZES mặc định chỉ có (3, 4).
STRESS_DIRECTORY = SOURCE_DIRECTORY / "benchmark" / "stress"

NAMES = ["Aaron", "Bella", "Caleb", "Diana", "Ethan", "Fiona", "George", "Hannah", "Isaac", "Julia",
         "Kevin", "Laura", "Mason", "Nora", "Oliver", "Paula", "Quinn", "Rosa", "Samuel", "Tara",
         "Umar", "Vera", "Wesley", "Xenia", "Yusuf"]
PROFESSIONS = ["Baker", "Doctor", "Farmer", "Teacher", "Pilot", "Guard", "Cook", "Judge", "Singer",
               "Painter", "Sailor", "Tailor", "Miner", "Clerk", "Hunter", "Nurse", "Smith", "Mayor",
               "Poet", "Driver", "Barber", "Butcher", "Gardener", "Priest", "Coder"]

# (puzzle_id, grid_size, kind, seed, thư mục). Bộ chuẩn dùng cho mọi so sánh.
CATALOG: list[tuple[str, int, str, int, Path]] = [
    *[(f"puzzle_3x3_{index:03d}", 3, "standard", DEFAULT_RANDOM_SEED + index, PUZZLE_DIRECTORY)
      for index in range(1, 6)],
    *[(f"puzzle_4x4_{index:03d}", 4, "standard", DEFAULT_RANDOM_SEED + 100 + index, PUZZLE_DIRECTORY)
      for index in range(1, 6)],
    *[(f"puzzle_5x5_{index:03d}", 5, "standard", DEFAULT_RANDOM_SEED + 200 + index, STRESS_DIRECTORY)
      for index in range(1, 3)],
    ("fixture_3x3_stuck", 3, "stuck", DEFAULT_RANDOM_SEED + 300, FIXTURE_DIRECTORY),
    ("fixture_4x4_ambiguous", 4, "ambiguous", DEFAULT_RANDOM_SEED + 400, FIXTURE_DIRECTORY),
    ("fixture_3x3_inconsistent", 3, "inconsistent", DEFAULT_RANDOM_SEED + 500, FIXTURE_DIRECTORY),
]

EXPECTED_STATE = {"standard": "SOLVED", "stuck": "STUCK", "ambiguous": "STUCK", "inconsistent": "INCONSISTENT"}


def _random_region(rng: Random, grid_size: int, owner_cell_id: str) -> dict[str, Any]:
    all_cell_ids = oracle.get_all_cell_ids(grid_size)
    kind = rng.choices(["ROW", "COLUMN", "NEIGHBORS", "EXPLICIT", "CORNERS", "BOUNDARY"],
                       weights=[3, 3, 4, 2, 1, 1])[0]
    if kind == "ROW":
        return {"type": "ROW", "row": rng.randint(1, grid_size)}
    if kind == "COLUMN":
        return {"type": "COLUMN", "column": chr(ord("A") + rng.randrange(grid_size))}
    if kind == "NEIGHBORS":
        center = owner_cell_id if rng.random() < 0.5 else rng.choice(all_cell_ids)
        return {"type": "NEIGHBORS", "cell_id": center}
    if kind == "EXPLICIT":
        chosen = set(rng.sample(all_cell_ids, rng.randint(2, min(4, len(all_cell_ids)))))
        return {"type": "EXPLICIT", "cell_ids": [cell for cell in all_cell_ids if cell in chosen]}
    return {"type": kind}


def random_clue(rng: Random, grid_size: int, owner_cell_id: str, solution: dict[str, bool],
                allow_fact: bool = True, loose: bool = False) -> dict[str, Any]:
    """Sinh một clue ngẫu nhiên đúng với ``solution``.

    ``loose=True`` ưu tiên AT_LEAST/AT_MOST lỏng để tạo ca mơ hồ.
    """
    clue_id = f"clue_{owner_cell_id.lower()}"
    all_cell_ids = oracle.get_all_cell_ids(grid_size)
    weights = [1 if allow_fact else 0, 2, 2, 6]
    kind = rng.choices(["FACT", "SAME", "DIFFERENT", "COUNT"], weights=weights)[0]
    if kind == "FACT":
        cell_id = rng.choice(all_cell_ids)
        return {"clue_id": clue_id, "type": "FACT", "cell_id": cell_id,
                "status": oracle.CRIMINAL if solution[cell_id] else oracle.INNOCENT}
    if kind in ("SAME", "DIFFERENT"):
        first, second = sorted(rng.sample(all_cell_ids, 2), key=all_cell_ids.index)
        clue_type = "SAME" if solution[first] == solution[second] else "DIFFERENT"
        return {"clue_id": clue_id, "type": clue_type, "cell_ids": [first, second]}
    region = _random_region(rng, grid_size, owner_cell_id)
    region_cell_ids = oracle.resolve_region(region, grid_size)
    criminal_count = sum(solution[cell] for cell in region_cell_ids)
    if loose:
        clue_type = rng.choice(["AT_LEAST", "AT_MOST"])
    else:
        clue_type = rng.choices(["EXACTLY", "AT_LEAST", "AT_MOST"], weights=[6, 2, 2])[0]
    if clue_type == "EXACTLY":
        k = criminal_count
    elif clue_type == "AT_LEAST":
        k = criminal_count if not loose else rng.randint(0, criminal_count)
    else:
        k = criminal_count if not loose else rng.randint(criminal_count, len(region_cell_ids))
    return {"clue_id": clue_id, "type": clue_type, "region": region, "k": k}


def _assemble(puzzle_id: str, grid_size: int, solution: dict[str, bool], clues: dict[str, dict[str, Any]],
              initial_revealed_cell_ids: list[str]) -> dict[str, Any]:
    cards = []
    for index, cell_id in enumerate(oracle.get_all_cell_ids(grid_size)):
        cards.append({"cell_id": cell_id, "name": NAMES[index], "profession": PROFESSIONS[index],
                      "status": oracle.CRIMINAL if solution[cell_id] else oracle.INNOCENT,
                      "clue": clues[cell_id]})
    return {"schema_version": SCHEMA_VERSION, "puzzle_id": puzzle_id, "grid_size": grid_size,
            "cards": cards, "initial_revealed_cell_ids": initial_revealed_cell_ids}


def _random_solution(rng: Random, grid_size: int) -> dict[str, bool]:
    all_cell_ids = oracle.get_all_cell_ids(grid_size)
    while True:
        solution = {cell: rng.random() < 0.4 for cell in all_cell_ids}
        if 0.25 <= sum(solution.values()) / len(all_cell_ids) <= 0.6:
            return solution


def generate_standard(puzzle_id: str, grid_size: int, seed: int) -> dict[str, Any]:
    """Sinh puzzle nghiệm duy nhất, giải hết bằng suy luận no-guess.

    Khi suy luận bị kẹt, clue của card vừa mở gần nhất (chưa bước nào dùng)
    được thay bằng clue đúng khác làm ép được ít nhất một ô mới. Ưu tiên clue
    đếm/quan hệ; FACT chỉ dùng khi không còn cách khác.
    """
    rng = Random(seed)
    all_cell_ids = oracle.get_all_cell_ids(grid_size)
    solution = _random_solution(rng, grid_size)
    clues = {cell: random_clue(rng, grid_size, cell, solution) for cell in all_cell_ids}
    initial_revealed_cell_ids = [rng.choice(all_cell_ids)]
    known = {cell: solution[cell] for cell in initial_revealed_cell_ids}
    reveal_order = list(initial_revealed_cell_ids)

    def first_forced() -> str | None:
        active = [clues[cell] for cell in known]
        for cell in all_cell_ids:
            if cell not in known and oracle.forced_status(active, known, cell, grid_size) is not None:
                return cell
        return None

    while len(known) < len(all_cell_ids):
        cell = first_forced()
        if cell is None:
            last_cell_id = reveal_order[-1]
            for attempt in range(200):
                clues[last_cell_id] = random_clue(rng, grid_size, last_cell_id, solution,
                                                  allow_fact=attempt >= 150)
                cell = first_forced()
                if cell is not None:
                    break
            else:
                raise RuntimeError(f"{puzzle_id}: không sửa được trạng thái STUCK")
        known[cell] = solution[cell]
        reveal_order.append(cell)
    return _assemble(puzzle_id, grid_size, solution, clues, initial_revealed_cell_ids)


def generate_random(puzzle_id: str, grid_size: int, seed: int, kind: str) -> dict[str, Any]:
    """Sinh ngẫu nhiên đến khi gặp ca ``stuck`` hoặc ``ambiguous`` theo yêu cầu."""
    rng = Random(seed)
    all_cell_ids = oracle.get_all_cell_ids(grid_size)
    for _ in range(5000):
        solution = _random_solution(rng, grid_size)
        clues = {cell: random_clue(rng, grid_size, cell, solution, loose=(kind == "ambiguous"))
                 for cell in all_cell_ids}
        puzzle = _assemble(puzzle_id, grid_size, solution, clues, [rng.choice(all_cell_ids)])
        model_count = oracle.count_models([card["clue"] for card in puzzle["cards"]], grid_size, limit=2)
        if (model_count == 1) != (kind == "stuck"):
            continue
        simulation = oracle.simulate_deduction(puzzle)
        if simulation["state"] == "STUCK" and simulation["steps"] >= 1:
            return puzzle
    raise RuntimeError(f"{puzzle_id}: không tìm được ca {kind}")


def generate_inconsistent(puzzle_id: str, grid_size: int, seed: int) -> dict[str, Any]:
    """Ca mâu thuẫn: bước 1 hợp lệ, clue vừa mở ở bước 1 mâu thuẫn KB."""
    rng = Random(seed)
    all_cell_ids = oracle.get_all_cell_ids(grid_size)
    solution = _random_solution(rng, grid_size)
    solution["A1"], solution["B1"] = False, True
    clues = {cell: random_clue(rng, grid_size, cell, solution) for cell in all_cell_ids}
    clues["A1"] = {"clue_id": "clue_a1", "type": "FACT", "cell_id": "B1", "status": oracle.CRIMINAL}
    # Clue sai so với nghiệm ẩn: nói A1 là criminal trong khi A1 đã công khai là innocent.
    clues["B1"] = {"clue_id": "clue_b1", "type": "FACT", "cell_id": "A1", "status": oracle.CRIMINAL}
    return _assemble(puzzle_id, grid_size, solution, clues, ["A1"])


def build_puzzle(puzzle_id: str, grid_size: int, kind: str, seed: int) -> dict[str, Any]:
    if kind == "standard":
        return generate_standard(puzzle_id, grid_size, seed)
    if kind in ("stuck", "ambiguous"):
        return generate_random(puzzle_id, grid_size, seed, kind)
    if kind == "inconsistent":
        return generate_inconsistent(puzzle_id, grid_size, seed)
    raise ValueError(f"kind: unknown {kind!r}")


def describe(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Tính các thuộc tính kiểm tra bằng oracle độc lập."""
    grid_size = puzzle["grid_size"]
    clues = [card["clue"] for card in puzzle["cards"]]
    solution = {card["cell_id"]: card["status"] == oracle.CRIMINAL for card in puzzle["cards"]}
    region_types = sorted({clue["region"]["type"] for clue in clues if "region" in clue})
    return {
        "puzzle_id": puzzle["puzzle_id"],
        "grid_size": grid_size,
        "clue_types": sorted({clue["type"] for clue in clues}),
        "region_types": region_types,
        "false_clue_ids": [clue["clue_id"] for clue in clues if not oracle.evaluate_clue(clue, solution, grid_size)],
        "model_count": oracle.count_models(clues, grid_size, limit=2),
        "deduction": oracle.simulate_deduction(puzzle),
    }


def check(puzzle: dict[str, Any], kind: str) -> list[str]:
    """Trả danh sách lỗi (rỗng nếu puzzle đúng loại mong đợi)."""
    info = describe(puzzle)
    errors = []
    state = info["deduction"]["state"]
    if state != EXPECTED_STATE[kind]:
        errors.append(f"deduction state {state}, expected {EXPECTED_STATE[kind]}")
    if kind in ("standard", "stuck"):
        if info["model_count"] != 1:
            errors.append(f"expected unique solution, got >= {info['model_count']}")
        if info["false_clue_ids"]:
            errors.append(f"clues false under hidden solution: {info['false_clue_ids']}")
    if kind == "ambiguous" and info["model_count"] < 2:
        errors.append("expected multiple solutions")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra file đã có, không ghi đè")
    args = parser.parse_args()

    failures = 0
    for puzzle_id, grid_size, kind, seed, directory in CATALOG:
        path = directory / f"{puzzle_id}.json"
        if args.check:
            puzzle = json.loads(path.read_text(encoding="utf-8"))
        else:
            puzzle = build_puzzle(puzzle_id, grid_size, kind, seed)
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(puzzle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        errors = check(puzzle, kind)
        info = describe(puzzle)
        failures += bool(errors)
        status = "OK " if not errors else "BAD"
        print(f"[{status}] {path.relative_to(SOURCE_DIRECTORY).as_posix():45s} kind={kind:12s} "
              f"state={info['deduction']['state']:12s} steps={info['deduction']['steps']:2d} "
              f"regions={','.join(info['region_types'])}")
        for error in errors:
            print(f"       - {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
