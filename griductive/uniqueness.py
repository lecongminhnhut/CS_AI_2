from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Any

from .encoder import encode
from .models import SatStatus, Status
from .sat import solve


class UniquenessClass(str, Enum):
    """Number of complete solutions of the full clue set."""

    UNIQUE = "UNIQUE"
    MULTIPLE = "MULTIPLE"
    UNSAT = "UNSAT"


@dataclass(frozen=True)
class UniquenessStats:
    """Totals over every SAT call made by the uniqueness check."""

    sat_calls: int
    decisions: int
    propagations: int
    backtracks: int
    runtime_ms: float


@dataclass(frozen=True)
class UniquenessResult:
    """Result of check_uniqueness()."""

    classification: UniquenessClass
    solution: dict[str, Status] | None          # the first model found (None if UNSAT)
    second_solution: dict[str, Status] | None   # a different model (only if MULTIPLE)
    matches_hidden_solution: bool | None        # does the first model equal the stored statuses?
    stats: UniquenessStats


def _field(record: Any, name: str) -> Any:
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


def _to_statuses(assignment: dict[int, bool], variable_map: dict[str, int]) -> dict[str, Status]:
    """Convert a SAT model to {cell_id: Status} using primary variables only."""
    return {cell_id: Status.CRIMINAL if assignment[var_id] else Status.INNOCENT
            for cell_id, var_id in variable_map.items()}


def check_uniqueness(puzzle: Any) -> UniquenessResult:
    """Classify the complete clue set of a puzzle as UNIQUE, MULTIPLE, or UNSAT."""
    started_at = perf_counter()
    cards = _field(puzzle, "cards")
    all_clues = [_field(card, "clue") for card in cards]

    # Build a KB from every clue
    kb = encode({"grid_size": _field(puzzle, "grid_size"),
                 "known_statuses": {}, "revealed_clues": all_clues})

    sat_results = []
    first = solve(kb.clauses, kb.num_variables)
    sat_results.append(first)

    solution = second_solution = None
    matches = None
    if first.status is SatStatus.UNSAT:
        classification = UniquenessClass.UNSAT
    else:
        solution = _to_statuses(first.assignment, kb.variable_map)
        hidden = {_field(card, "cell_id"): Status(_field(card, "status")) for card in cards}
        matches = solution == hidden

        # Blocking clause: "at least one primary variable differs from this model".
        blocking_clause = [-var_id if first.assignment[var_id] else var_id
                           for var_id in kb.variable_map.values()]
        second = solve(kb.clauses + [blocking_clause], kb.num_variables)
        sat_results.append(second)

        if second.status is SatStatus.UNSAT:
            classification = UniquenessClass.UNIQUE
        else:
            classification = UniquenessClass.MULTIPLE
            second_solution = _to_statuses(second.assignment, kb.variable_map)

    stats = UniquenessStats(
        sat_calls=len(sat_results),
        decisions=sum(r.stats.decisions for r in sat_results),
        propagations=sum(r.stats.propagations for r in sat_results),
        backtracks=sum(r.stats.backtracks for r in sat_results),
        runtime_ms=(perf_counter() - started_at) * 1000.0,
    )
    return UniquenessResult(classification, solution, second_solution, matches, stats)


if __name__ == "__main__":
    import sys

    from .models import load_puzzle

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m griductive.uniqueness <puzzle.json> [more.json ...]")
    for path in sys.argv[1:]:
        result = check_uniqueness(load_puzzle(path))
        print(f"{path}: {result.classification.value} "
              f"(matches stored solution: {result.matches_hidden_solution}, "
              f"SAT calls: {result.stats.sat_calls}, decisions: {result.stats.decisions}, "
              f"{result.stats.runtime_ms:.1f} ms)")
