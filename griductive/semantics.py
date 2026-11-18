"""Direct semantic evaluator for Griductive clues (section 4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Clue, ClueType, Status, validate_clue
from .regions import get_all_cell_ids, resolve_region


def _normalize_assignment(
    cell_assignment: Mapping[str, bool | Status],
    grid_size: int,
) -> dict[str, bool]:
    if not isinstance(cell_assignment, Mapping):
        raise ValueError("cell_assignment: expected mapping from cell_id to bool or Status")
    expected_cells = get_all_cell_ids(grid_size)
    if set(cell_assignment.keys()) != set(expected_cells):
        missing = sorted(set(expected_cells) - set(cell_assignment.keys()))
        extra = sorted(set(cell_assignment.keys()) - set(expected_cells))
        raise ValueError(f"cell_assignment: incomplete or unknown cells (missing={missing}, extra={extra})")

    normalized: dict[str, bool] = {}
    for cell_id in expected_cells:
        value = cell_assignment[cell_id]
        if isinstance(value, Status):
            normalized[cell_id] = value.to_bool()
        elif isinstance(value, bool):
            normalized[cell_id] = value
        else:
            raise ValueError(f"cell_assignment[{cell_id!r}]: expected bool or Status, got {value!r}")
    return normalized


def evaluate_clue(
    clue: Clue | Mapping[str, Any],
    cell_assignment: Mapping[str, bool | Status],
    grid_size: int,
) -> bool:
    """Evaluate a clue directly under a complete assignment without calling the CNF encoder."""
    validated = validate_clue(clue, grid_size)
    assignment = _normalize_assignment(cell_assignment, grid_size)

    if validated.type is ClueType.FACT:
        return assignment[validated.cell_id] == validated.status.to_bool()  # type: ignore[index, union-attr]

    if validated.type is ClueType.SAME:
        c1, c2 = validated.cell_ids  # type: ignore[misc]
        return assignment[c1] == assignment[c2]

    if validated.type is ClueType.DIFFERENT:
        c1, c2 = validated.cell_ids  # type: ignore[misc]
        return assignment[c1] != assignment[c2]

    region_cells = resolve_region(validated.region, grid_size)
    criminal_count = sum(1 for cell_id in region_cells if assignment[cell_id])
    k = validated.k  # type: ignore[assignment]

    if validated.type is ClueType.EXACTLY:
        return criminal_count == k
    if validated.type is ClueType.AT_LEAST:
        return criminal_count >= k
    return criminal_count <= k
