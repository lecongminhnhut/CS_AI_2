"""Automatic CNF encoder for Griductive clues and PublicState (section 4.2)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import combinations
from typing import Any

from .models import Clue, ClueType, EncodedKB, PublicState, Status, validate_clue
from .regions import get_all_cell_ids, parse_cell_id, resolve_region

COMBINATORIAL_CLAUSE_LIMIT = 100


class AuxiliaryVariableAllocator:
    """Sequential allocator for auxiliary CNF variable IDs."""

    def __init__(self, start_var_id: int) -> None:
        if isinstance(start_var_id, bool) or not isinstance(start_var_id, int) or start_var_id < 1:
            raise ValueError(f"start_var_id: expected positive int, got {start_var_id!r}")
        self.start_var_id = start_var_id
        self.next_auxiliary_var_id = start_var_id

    @property
    def count(self) -> int:
        """Number of auxiliary variables allocated so far."""
        return self.next_auxiliary_var_id - self.start_var_id

    def allocate(self) -> int:
        """Allocate and return the next auxiliary variable ID."""
        var_id = self.next_auxiliary_var_id
        self.next_auxiliary_var_id += 1
        return var_id


def build_variable_map(grid_size: int) -> dict[str, int]:
    """Build deterministic primary variable map cell_id -> 1..N^2 in row-major order."""
    return {cell_id: index for index, cell_id in enumerate(get_all_cell_ids(grid_size), start=1)}


def _combinatorial_at_most(literals: list[int], k: int) -> list[list[int]]:
    """Direct combinatorial CNF for sum(literals) <= k."""
    m = len(literals)
    if k >= m:
        return []
    if k == 0:
        return [[-lit] for lit in literals]
    return [[-lit for lit in subset] for subset in combinations(literals, k + 1)]


def _sequential_at_most(
    literals: list[int],
    k: int,
    allocator: AuxiliaryVariableAllocator,
) -> list[list[int]]:
    """Sinz sequential counter CNF for sum(literals) <= k with 1 <= k < len(literals)."""
    m = len(literals)
    if k >= m:
        return []
    if k == 0:
        return [[-lit] for lit in literals]
    if k == m - 1:
        return [[-lit for lit in literals]]

    # s[i][j] holds iff at least (j + 1) of literals[0..i] are True (0 <= i < m - 1, 0 <= j < k).
    s = [[allocator.allocate() for _ in range(k)] for _ in range(m - 1)]
    clauses: list[list[int]] = []

    clauses.append([-literals[0], s[0][0]])
    for j in range(1, k):
        clauses.append([-s[0][j]])

    for i in range(1, m - 1):
        clauses.append([-literals[i], s[i][0]])
        clauses.append([-s[i - 1][0], s[i][0]])
        for j in range(1, k):
            clauses.append([-s[i - 1][j], s[i][j]])
            clauses.append([-literals[i], -s[i - 1][j - 1], s[i][j]])
        clauses.append([-literals[i], -s[i - 1][k - 1]])

    clauses.append([-literals[m - 1], -s[m - 2][k - 1]])
    return clauses


def _encode_at_most(
    literals: list[int],
    k: int,
    allocator: AuxiliaryVariableAllocator,
) -> list[list[int]]:
    """Encode sum(literals) <= k using combinatorial CNF when compact, else sequential counter."""
    m = len(literals)
    if k >= m:
        return []
    if k == 0:
        return [[-lit] for lit in literals]
    if math.comb(m, k + 1) <= COMBINATORIAL_CLAUSE_LIMIT:
        return _combinatorial_at_most(literals, k)
    return _sequential_at_most(literals, k, allocator)


def _encode_at_least(
    literals: list[int],
    k: int,
    allocator: AuxiliaryVariableAllocator,
) -> list[list[int]]:
    """Encode sum(literals) >= k as sum(-literals) <= len(literals) - k."""
    return _encode_at_most([-lit for lit in literals], len(literals) - k, allocator)


def encode_clue(
    clue: Clue | Mapping[str, Any],
    variable_map: Mapping[str, int],
    grid_size: int,
    allocator: AuxiliaryVariableAllocator | None = None,
) -> list[list[int]]:
    """Convert a single validated clue into CNF clauses."""
    validated = validate_clue(clue, grid_size)
    if allocator is None:
        allocator = AuxiliaryVariableAllocator(len(variable_map) + 1)

    if validated.type is ClueType.FACT:
        var_id = variable_map[validated.cell_id]  # type: ignore[index]
        return [[var_id if validated.status.to_bool() else -var_id]]  # type: ignore[union-attr]

    if validated.type is ClueType.SAME:
        c1, c2 = validated.cell_ids  # type: ignore[misc]
        v1, v2 = variable_map[c1], variable_map[c2]
        return [[-v1, v2], [v1, -v2]]

    if validated.type is ClueType.DIFFERENT:
        c1, c2 = validated.cell_ids  # type: ignore[misc]
        v1, v2 = variable_map[c1], variable_map[c2]
        return [[v1, v2], [-v1, -v2]]

    region_cells = resolve_region(validated.region, grid_size)
    region_vars = [variable_map[cell_id] for cell_id in region_cells]
    k = validated.k  # type: ignore[assignment]

    if validated.type is ClueType.AT_MOST:
        return _encode_at_most(region_vars, k, allocator)
    if validated.type is ClueType.AT_LEAST:
        return _encode_at_least(region_vars, k, allocator)
    # ClueType.EXACTLY
    return _encode_at_least(region_vars, k, allocator) + _encode_at_most(region_vars, k, allocator)


def _field(record: Any, name: str) -> Any:
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


def encode(public_state: PublicState | Mapping[str, Any]) -> EncodedKB:
    """Build KB_t = CNF(revealed_clues) & unit clauses for known_statuses from PublicState."""
    grid_size = _field(public_state, "grid_size")
    known_statuses = _field(public_state, "known_statuses")
    revealed_clues = _field(public_state, "revealed_clues")

    variable_map = build_variable_map(grid_size)
    reverse_variable_map = {var_id: cell_id for cell_id, var_id in variable_map.items()}
    allocator = AuxiliaryVariableAllocator(len(variable_map) + 1)
    clauses: list[list[int]] = []

    for clue in revealed_clues:
        clauses.extend(encode_clue(clue, variable_map, grid_size, allocator))

    if not isinstance(known_statuses, Mapping):
        raise ValueError("public_state.known_statuses: expected mapping")
    for cell_id in sorted(known_statuses):
        parse_cell_id(cell_id, grid_size)
        status = Status(known_statuses[cell_id])
        var_id = variable_map[cell_id]
        clauses.append([var_id if status.to_bool() else -var_id])

    num_primary = len(variable_map)
    num_aux = allocator.count
    return EncodedKB(
        clauses=clauses,
        variable_map=variable_map,
        reverse_variable_map=reverse_variable_map,
        num_primary_variables=num_primary,
        num_auxiliary_variables=num_aux,
        num_variables=num_primary + num_aux,
        num_clauses=len(clauses),
    )
