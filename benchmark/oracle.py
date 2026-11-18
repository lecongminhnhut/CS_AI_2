"""Bộ giải đối chứng độc lập cho phần 4.5 (không dùng CNF/DPLL của nhóm).

Module này chỉ đọc puzzle JSON dạng dict theo TEAM_CONVENTIONS 1.0.0 và tìm
model bằng backtracking có cắt tỉa theo cận đếm. Nó dùng cho:

- ``generate_puzzles.py``: kiểm tra puzzle sinh ra có nghiệm duy nhất và giải
  được bằng vòng suy luận no-guess (không STUCK);
- ``tests/test_integration.py``: đối chiếu kết quả của encoder/DPLL/agent với
  một cách giải khác hoàn toàn (yêu cầu "DPLL khớp brute force" ở mục 11).

Không import bất kỳ module nào trong package ``griductive``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

CRIMINAL = "CRIMINAL"
INNOCENT = "INNOCENT"


def get_all_cell_ids(grid_size: int) -> list[str]:
    """Trả mọi cell_id theo row-major: A1, B1, ..., A2, ..."""
    return [f"{chr(ord('A') + column_index)}{row_index + 1}"
            for row_index in range(grid_size) for column_index in range(grid_size)]


def parse_cell_id(cell_id: str, grid_size: int) -> tuple[int, int]:
    """Trả ``(row_index, column_index)`` bắt đầu từ 0; ValueError nếu sai."""
    if (not isinstance(cell_id, str) or len(cell_id) < 2 or not cell_id[0].isupper()
            or not cell_id[1:].isdigit() or cell_id[1] == "0"):
        raise ValueError(f"cell_id: invalid {cell_id!r}")
    row_index, column_index = int(cell_id[1:]) - 1, ord(cell_id[0]) - ord("A")
    if not (0 <= row_index < grid_size and 0 <= column_index < grid_size):
        raise ValueError(f"cell_id: outside board {cell_id!r}")
    return row_index, column_index


def resolve_region(region: dict[str, Any], grid_size: int) -> list[str]:
    """Phân giải region thành danh sách cell_id theo row-major (cài độc lập)."""
    all_cell_ids = get_all_cell_ids(grid_size)
    last = grid_size - 1
    kind = region["type"]
    if kind == "ROW":
        selected = {cell for cell in all_cell_ids if parse_cell_id(cell, grid_size)[0] == region["row"] - 1}
    elif kind == "COLUMN":
        selected = {cell for cell in all_cell_ids if cell[0] == region["column"]}
    elif kind == "NEIGHBORS":
        row_index, column_index = parse_cell_id(region["cell_id"], grid_size)
        selected = set()
        for cell in all_cell_ids:
            other_row, other_column = parse_cell_id(cell, grid_size)
            if cell != region["cell_id"] and abs(other_row - row_index) <= 1 and abs(other_column - column_index) <= 1:
                selected.add(cell)
    elif kind == "EXPLICIT":
        selected = set(region["cell_ids"])
    elif kind == "CORNERS":
        selected = {cell for cell in all_cell_ids
                    if all(index in (0, last) for index in parse_cell_id(cell, grid_size))}
    elif kind == "BOUNDARY":
        selected = {cell for cell in all_cell_ids
                    if any(index in (0, last) for index in parse_cell_id(cell, grid_size))}
    else:
        raise ValueError(f"region.type: unknown {kind!r}")
    return [cell for cell in all_cell_ids if cell in selected]


def evaluate_clue(clue: dict[str, Any], cell_assignment: dict[str, bool], grid_size: int) -> bool:
    """Evaluator trực tiếp, độc lập với ``griductive.semantics``."""
    kind = clue["type"]
    if kind == "FACT":
        return cell_assignment[clue["cell_id"]] == (clue["status"] == CRIMINAL)
    if kind in ("SAME", "DIFFERENT"):
        first, second = clue["cell_ids"]
        return (cell_assignment[first] == cell_assignment[second]) == (kind == "SAME")
    criminal_count = sum(cell_assignment[cell] for cell in resolve_region(clue["region"], grid_size))
    return {"EXACTLY": criminal_count == clue["k"], "AT_LEAST": criminal_count >= clue["k"],
            "AT_MOST": criminal_count <= clue["k"]}[kind]


class _Constraint:
    """Ràng buộc đã chuẩn hóa: đếm trong [lower, upper] hoặc quan hệ hai ô."""

    __slots__ = ("kind", "indices", "lower", "upper")

    def __init__(self, kind: str, indices: list[int], lower: int = 0, upper: int = 0) -> None:
        self.kind, self.indices, self.lower, self.upper = kind, indices, lower, upper


def _compile(clues: Iterable[dict[str, Any]], fixed: dict[str, bool], grid_size: int) -> list[_Constraint]:
    index_of = {cell: index for index, cell in enumerate(get_all_cell_ids(grid_size))}
    constraints = []
    for clue in clues:
        kind = clue["type"]
        if kind == "FACT":
            value = int(clue["status"] == CRIMINAL)
            constraints.append(_Constraint("COUNT", [index_of[clue["cell_id"]]], value, value))
        elif kind in ("SAME", "DIFFERENT"):
            constraints.append(_Constraint(kind, [index_of[cell] for cell in clue["cell_ids"]]))
        else:
            indices = [index_of[cell] for cell in resolve_region(clue["region"], grid_size)]
            lower = clue["k"] if kind in ("EXACTLY", "AT_LEAST") else 0
            upper = clue["k"] if kind in ("EXACTLY", "AT_MOST") else len(indices)
            constraints.append(_Constraint("COUNT", indices, lower, upper))
    for cell, value in fixed.items():
        constraints.append(_Constraint("COUNT", [index_of[cell]], int(value), int(value)))
    return constraints


def _violated(constraint: _Constraint, values: list[int | None]) -> bool:
    if constraint.kind == "COUNT":
        criminal_count = unknown = 0
        for index in constraint.indices:
            value = values[index]
            if value is None:
                unknown += 1
            else:
                criminal_count += value
        return criminal_count > constraint.upper or criminal_count + unknown < constraint.lower
    first, second = (values[index] for index in constraint.indices)
    if first is None or second is None:
        return False
    return (first == second) != (constraint.kind == "SAME")


def iter_models(clues: Iterable[dict[str, Any]], grid_size: int,
                fixed: dict[str, bool] | None = None) -> Iterator[dict[str, bool]]:
    """Liệt kê mọi assignment thỏa các clue và các ô cố định, theo thứ tự tất định."""
    all_cell_ids = get_all_cell_ids(grid_size)
    constraints = _compile(clues, fixed or {}, grid_size)
    watched: list[list[_Constraint]] = [[] for _ in all_cell_ids]
    for constraint in constraints:
        for index in constraint.indices:
            watched[index].append(constraint)
    if any(_violated(constraint, [None] * len(all_cell_ids)) for constraint in constraints):
        return
    values: list[int | None] = [None] * len(all_cell_ids)
    # Ô có ràng buộc được gán trước (row-major); ô tự do để cuối để chứng minh
    # UNSAT không phải duyệt 2^k nhánh vô ích.
    search_order = ([index for index in range(len(all_cell_ids)) if watched[index]]
                    + [index for index in range(len(all_cell_ids)) if not watched[index]])

    def search(position: int) -> Iterator[dict[str, bool]]:
        if position == len(search_order):
            yield {cell: bool(values[i]) for i, cell in enumerate(all_cell_ids)}
            return
        index = search_order[position]
        for value in (0, 1):
            values[index] = value
            if not any(_violated(constraint, values) for constraint in watched[index]):
                yield from search(position + 1)
        values[index] = None

    yield from search(0)


def find_model(clues: Iterable[dict[str, Any]], grid_size: int,
               fixed: dict[str, bool] | None = None) -> dict[str, bool] | None:
    """Trả một model bất kỳ hoặc None nếu không tồn tại."""
    return next(iter_models(list(clues), grid_size, fixed), None)


def count_models(clues: Iterable[dict[str, Any]], grid_size: int, limit: int = 2) -> int:
    """Đếm model, dừng sớm khi đạt ``limit``."""
    count = 0
    for _ in iter_models(list(clues), grid_size):
        count += 1
        if count >= limit:
            break
    return count


def forced_status(clues: list[dict[str, Any]], known: dict[str, bool], cell_id: str,
                  grid_size: int) -> str | None:
    """CRIMINAL/INNOCENT nếu bị ép bởi KB công khai, ngược lại None."""
    if find_model(clues, grid_size, {**known, cell_id: False}) is None:
        return CRIMINAL
    if find_model(clues, grid_size, {**known, cell_id: True}) is None:
        return INNOCENT
    return None


def simulate_deduction(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Mô phỏng vòng suy luận no-guess chỉ trên dữ liệu công khai.

    Trả dict gồm ``state`` (SOLVED/STUCK/INCONSISTENT), ``steps`` (số verdict
    được chấp nhận), ``order`` (cell_id theo thứ tự mở) và ``mismatch`` (True
    nếu một verdict được chứng minh lại trái với status ẩn, tức dữ liệu lỗi).
    """
    grid_size = puzzle["grid_size"]
    cards = {card["cell_id"]: card for card in puzzle["cards"]}
    known = {cell: cards[cell]["status"] == CRIMINAL for cell in puzzle["initial_revealed_cell_ids"]}
    order: list[str] = []
    while True:
        clues = [cards[cell]["clue"] for cell in known]
        if find_model(clues, grid_size, known) is None:
            return {"state": "INCONSISTENT", "steps": len(order), "order": order, "mismatch": False}
        unresolved = [cell for cell in get_all_cell_ids(grid_size) if cell not in known]
        if not unresolved:
            return {"state": "SOLVED", "steps": len(order), "order": order, "mismatch": False}
        for cell in unresolved:
            verdict = forced_status(clues, known, cell, grid_size)
            if verdict is not None:
                break
        else:
            return {"state": "STUCK", "steps": len(order), "order": order, "mismatch": False}
        if verdict != cards[cell]["status"]:
            return {"state": "ERROR", "steps": len(order), "order": order, "mismatch": True}
        known[cell] = verdict == CRIMINAL
        order.append(cell)
