"""Board coordinate helpers and region resolution for Griductive (section 4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _field(record: Any, name: str) -> Any:
    return record[name] if isinstance(record, Mapping) else getattr(record, name, None)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _validate_grid_size(grid_size: int) -> int:
    if isinstance(grid_size, bool) or not isinstance(grid_size, int) or not (1 <= grid_size <= 26):
        raise ValueError(f"grid_size: expected int in 1..26, got {grid_size!r}")
    return grid_size


def get_all_cell_ids(grid_size: int) -> list[str]:
    """Return all cell IDs in deterministic row-major order (A1, B1, ..., A2, ...)."""
    size = _validate_grid_size(grid_size)
    return [
        f"{chr(ord('A') + col_index)}{row_index + 1}"
        for row_index in range(size)
        for col_index in range(size)
    ]


def parse_cell_id(cell_id: str, grid_size: int) -> tuple[int, int]:
    """Parse a cell ID like 'C2' into 0-based (row_index, column_index)."""
    size = _validate_grid_size(grid_size)
    if (
        not isinstance(cell_id, str)
        or len(cell_id) < 2
        or not cell_id[0].isupper()
        or not cell_id[1:].isdigit()
        or cell_id[1] == "0"
    ):
        raise ValueError(f"cell_id: invalid {cell_id!r}")
    row_index = int(cell_id[1:]) - 1
    col_index = ord(cell_id[0]) - ord("A")
    if not (0 <= row_index < size and 0 <= col_index < size):
        raise ValueError(f"cell_id: outside {size}x{size} board: {cell_id!r}")
    return row_index, col_index


def format_cell_id(row_index: int, col_index: int, grid_size: int) -> str:
    """Format 0-based (row_index, col_index) as a cell ID."""
    size = _validate_grid_size(grid_size)
    if (
        isinstance(row_index, bool)
        or isinstance(col_index, bool)
        or not isinstance(row_index, int)
        or not isinstance(col_index, int)
        or not (0 <= row_index < size and 0 <= col_index < size)
    ):
        raise ValueError(f"coordinates ({row_index!r}, {col_index!r}) out of bounds for size {size}")
    return f"{chr(ord('A') + col_index)}{row_index + 1}"


def resolve_region(region: Any, grid_size: int) -> list[str]:
    """Validate a region specification and return matching cell IDs in row-major order."""
    size = _validate_grid_size(grid_size)
    if not isinstance(region, Mapping) and not hasattr(region, "type"):
        raise ValueError("region: expected a region mapping or RegionSpec")

    region_type = _enum_value(_field(region, "type"))
    all_cells = get_all_cell_ids(size)
    last = size - 1

    if region_type == "ROW":
        row = _field(region, "row")
        if isinstance(row, bool) or not isinstance(row, int) or not (1 <= row <= size):
            raise ValueError(f"region.row: expected int in 1..{size}, got {row!r}")
        selected = {cell for cell in all_cells if parse_cell_id(cell, size)[0] == row - 1}
        return [cell for cell in all_cells if cell in selected]

    if region_type == "COLUMN":
        column = _field(region, "column")
        max_col = chr(ord("A") + size - 1)
        if not isinstance(column, str) or len(column) != 1 or not ("A" <= column <= max_col):
            raise ValueError(f"region.column: expected 'A'..'{max_col}', got {column!r}")
        selected = {cell for cell in all_cells if cell[0] == column}
        return [cell for cell in all_cells if cell in selected]

    if region_type == "NEIGHBORS":
        center = _field(region, "cell_id")
        r0, c0 = parse_cell_id(center, size)
        selected = set()
        for cell in all_cells:
            r, c = parse_cell_id(cell, size)
            if cell != center and abs(r - r0) <= 1 and abs(c - c0) <= 1:
                selected.add(cell)
        return [cell for cell in all_cells if cell in selected]

    if region_type == "EXPLICIT":
        cell_ids = _field(region, "cell_ids")
        if not isinstance(cell_ids, (list, tuple)):
            raise ValueError("region.cell_ids: expected list[str]")
        selected = set()
        for cell in cell_ids:
            parse_cell_id(cell, size)
            if cell in selected:
                raise ValueError(f"region.cell_ids: duplicate cell_id {cell!r}")
            selected.add(cell)
        return [cell for cell in all_cells if cell in selected]

    if region_type == "CORNERS":
        selected = {
            cell
            for cell in all_cells
            if all(idx in (0, last) for idx in parse_cell_id(cell, size))
        }
        return [cell for cell in all_cells if cell in selected]

    if region_type == "BOUNDARY":
        selected = {
            cell
            for cell in all_cells
            if any(idx in (0, last) for idx in parse_cell_id(cell, size))
        }
        return [cell for cell in all_cells if cell in selected]

    raise ValueError(f"region.type: unsupported region type {region_type!r}")


def get_referenced_cell_ids(clue: Any, grid_size: int) -> list[str]:
    """Return cell IDs referenced or counted by a clue (used for UI highlighting)."""
    size = _validate_grid_size(grid_size)
    clue_type = _enum_value(_field(clue, "type"))

    if clue_type == "FACT":
        cell_id = _field(clue, "cell_id")
        parse_cell_id(cell_id, size)
        return [cell_id]

    if clue_type in ("SAME", "DIFFERENT"):
        cell_ids = _field(clue, "cell_ids")
        if not isinstance(cell_ids, (list, tuple)) or len(cell_ids) != 2:
            raise ValueError(f"{clue_type}.cell_ids: expected 2 cell IDs")
        for cell_id in cell_ids:
            parse_cell_id(cell_id, size)
        return list(dict.fromkeys(cell_ids))

    if clue_type in ("EXACTLY", "AT_LEAST", "AT_MOST"):
        return resolve_region(_field(clue, "region"), size)

    raise ValueError(f"clue.type: unsupported clue type {clue_type!r}")
