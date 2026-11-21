from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .encoder import encode
from .models import EncodedKB, SatStatus, SolverStats, Status
from .sat import solve


class Classification(str, Enum):
    """Verdict of the agent for one unresolved character."""

    CRIMINAL = "CRIMINAL"
    INNOCENT = "INNOCENT"
    UNKNOWN = "UNKNOWN"
    INCONSISTENT = "INCONSISTENT"


class MoveState(str, Enum):
    """State returned by next_move()."""

    MOVE_AVAILABLE = "MOVE_AVAILABLE"  
    SOLVED = "SOLVED"                  
    STUCK = "STUCK"                   
    INCONSISTENT = "INCONSISTENT"     


@dataclass(frozen=True)
class SatQuery:
    """One call to the DPLL solver, kept for the deduction trace and statistics."""

    purpose: str              # "CONSISTENCY", "TEST_NOT_CRIMINAL" or "TEST_NOT_INNOCENT"
    cell_id: str | None       # the character being tested (None for CONSISTENCY)
    assumptions: list[int]    # temporary literals added for this call
    status: SatStatus         # SAT or UNSAT
    stats: SolverStats        # decisions, propagations, backtracks, runtime_ms


@dataclass(frozen=True)
class ClassificationResult:
    """Classification of one character, plus the SAT queries used to prove it."""

    cell_id: str
    classification: Classification
    sat_queries: list[SatQuery]


@dataclass(frozen=True)
class MoveResult:
    """Answer of next_move(): what the agent wants to do next."""

    state: MoveState
    cell_id: str | None
    verdict: Status | None
    sat_queries: list[SatQuery]


@dataclass
class AutoSolveResult:
    """Outcome of auto_solve(): final state plus the deduction trace."""

    state: MoveState
    trace: list[dict[str, Any]] = field(default_factory=list)
    sat_queries: list[SatQuery] = field(default_factory=list)


def _field(record: Any, name: str) -> Any:
    """Read a field from a dataclass or a dict (the team code accepts both)."""
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


def _ask_sat(kb: EncodedKB, purpose: str, cell_id: str | None, assumptions: list[int],
             queries: list[SatQuery], witnesses: list[dict[int, bool]]) -> bool:
    """Run DPLL on KB plus temporary assumptions, record the call, return True if SAT."""
    result = solve(kb.clauses, kb.num_variables, assumptions)
    queries.append(SatQuery(purpose=purpose, cell_id=cell_id, assumptions=list(assumptions),
                            status=result.status, stats=result.stats))
    if result.status is SatStatus.SAT:
        witnesses.append(result.assignment)
        return True
    return False


def _is_consistent(kb: EncodedKB, queries: list[SatQuery],
                   witnesses: list[dict[int, bool]]) -> bool:
    """Return True when KB itself has at least one model."""
    return _ask_sat(kb, "CONSISTENCY", None, [], queries, witnesses)


def _classify_cell(kb: EncodedKB, cell_id: str, queries: list[SatQuery],
                   witnesses: list[dict[int, bool]]) -> Classification:
    """Classify one cell on an already consistent KB."""
    var_id = kb.variable_map[cell_id]
    can_be_innocent = any(not model[var_id] for model in witnesses)
    can_be_criminal = any(model[var_id] for model in witnesses)

    # Assume the character is INNOCENT (not C_i). If impossible, they must be CRIMINAL.
    if not can_be_innocent:
        can_be_innocent = _ask_sat(kb, "TEST_NOT_CRIMINAL", cell_id, [-var_id], queries, witnesses)
        if not can_be_innocent:
            return Classification.CRIMINAL

    # Assume the character is CRIMINAL (C_i). If impossible, they must be INNOCENT.
    if not can_be_criminal:
        can_be_criminal = _ask_sat(kb, "TEST_NOT_INNOCENT", cell_id, [var_id], queries, witnesses)
        if not can_be_criminal:
            return Classification.INNOCENT

    # Both statuses appear in some model: the public evidence does not decide this cell.
    return Classification.UNKNOWN


def _unresolved_cells(public_state: Any) -> list[str]:
    """Cells without a proved verdict, in row-major order (deterministic choice)."""
    known = _field(public_state, "known_statuses")
    cards = _field(public_state, "cards")  # GameEngine keeps cards in row-major order
    return [_field(card, "cell_id") for card in cards if _field(card, "cell_id") not in known]


def classify(public_state: Any, cell_id: str) -> ClassificationResult:
    """Classify one character as CRIMINAL, INNOCENT, UNKNOWN, or INCONSISTENT."""
    kb = encode(public_state)
    if cell_id not in kb.variable_map:
        raise ValueError(f"cell_id: {cell_id!r} is not on this board")

    queries: list[SatQuery] = []
    witnesses: list[dict[int, bool]] = []
    if not _is_consistent(kb, queries, witnesses):
        return ClassificationResult(cell_id, Classification.INCONSISTENT, queries)

    known = _field(public_state, "known_statuses")
    if cell_id in known:  # already proved earlier: no new query needed
        return ClassificationResult(cell_id, Classification(Status(known[cell_id]).value), queries)

    return ClassificationResult(cell_id, _classify_cell(kb, cell_id, queries, witnesses), queries)


def classify_all(public_state: Any) -> dict[str, ClassificationResult]:
    """Classify every unresolved character. The KB is encoded and checked only once."""
    kb = encode(public_state)
    consistency_queries: list[SatQuery] = []
    witnesses: list[dict[int, bool]] = []  # shared by all cells: same KB
    consistent = _is_consistent(kb, consistency_queries, witnesses)

    results: dict[str, ClassificationResult] = {}
    for index, cell_id in enumerate(_unresolved_cells(public_state)):
        queries = list(consistency_queries) if index == 0 else []
        if consistent:
            verdict = _classify_cell(kb, cell_id, queries, witnesses)
        else:
            verdict = Classification.INCONSISTENT
        results[cell_id] = ClassificationResult(cell_id, verdict, queries)
    return results


def next_move(public_state: Any) -> MoveResult:
    """Return the first forced verdict in row-major order, or a terminal state."""
    kb = encode(public_state)
    queries: list[SatQuery] = []
    witnesses: list[dict[int, bool]] = []  # models of this KB, reused across cells

    if not _is_consistent(kb, queries, witnesses):
        return MoveResult(MoveState.INCONSISTENT, None, None, queries)

    unresolved = _unresolved_cells(public_state)
    if not unresolved:
        return MoveResult(MoveState.SOLVED, None, None, queries)

    for cell_id in unresolved:
        verdict = _classify_cell(kb, cell_id, queries, witnesses)
        if verdict is not Classification.UNKNOWN:
            return MoveResult(MoveState.MOVE_AVAILABLE, cell_id, Status(verdict.value), queries)

    return MoveResult(MoveState.STUCK, None, None, queries)


def explain_move(public_state: Any, cell_id: str, verdict: Status | str) -> list[str]:
    """Return a small set of revealed clue IDs that is enough to prove the verdict."""
    verdict = Status(verdict)
    clues = list(_field(public_state, "revealed_clues"))
    base = {"grid_size": _field(public_state, "grid_size"),
            "known_statuses": dict(_field(public_state, "known_statuses"))}

    def still_proves(clue_subset: list[Any]) -> bool:
        kb = encode({**base, "revealed_clues": clue_subset})
        var_id = kb.variable_map[cell_id]
        opposite = -var_id if verdict is Status.CRIMINAL else var_id
        return solve(kb.clauses, kb.num_variables, [opposite]).status is SatStatus.UNSAT

    if not still_proves(clues):
        return []  # verdict is not forced: nothing to explain

    needed = clues
    for clue in clues:
        candidate = [other for other in needed if other is not clue]
        if still_proves(candidate):
            needed = candidate
    return [_field(clue, "clue_id") for clue in needed]


def auto_solve(engine: Any, max_steps: int | None = None) -> AutoSolveResult:
    """Run the full deduction loop against a GameEngine and return the trace."""
    public_state = engine.get_public_state()
    if max_steps is None:
        max_steps = len(_field(public_state, "cards")) + 1
    outcome = AutoSolveResult(state=MoveState.STUCK)

    for _ in range(max_steps):
        move = next_move(public_state)
        outcome.sat_queries.extend(move.sat_queries)
        if move.state is not MoveState.MOVE_AVAILABLE:
            outcome.state = move.state
            return outcome

        active_clue_ids = [_field(clue, "clue_id") for clue in _field(public_state, "revealed_clues")]
        verdict_result = engine.submit_verdict(move.cell_id, move.verdict)
        outcome.sat_queries.extend(_field(verdict_result, "sat_queries"))
        result = _field(verdict_result, "result")
        if result != "ACCEPTED":
            raise RuntimeError(f"Engine rejected proved verdict {move.cell_id}={move.verdict.value}: {result}")

        outcome.trace.append({
            "step": len(outcome.trace) + 1,
            "active_clue_ids": active_clue_ids,
            "sat_queries": list(move.sat_queries),
            "cell_id": move.cell_id,
            "verdict": move.verdict.value,
            "newly_revealed_clue": _field(verdict_result, "newly_revealed_clue"),
        })
        public_state = _field(verdict_result, "public_state")

    raise RuntimeError(f"No terminal state after {max_steps} steps")


def _main() -> None:
    """Run the agent on one puzzle file and print the deduction trace."""
    import sys

    from .engine import GameEngine
    from .models import load_puzzle

    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m griductive.agent <puzzle.json>")
    engine = GameEngine(load_puzzle(sys.argv[1]))
    outcome = auto_solve(engine)
    for entry in outcome.trace:
        clue = entry["newly_revealed_clue"]
        queries = " ".join(f"{q.purpose}({q.cell_id or '-'})={q.status.value}" for q in entry["sat_queries"])
        print(f"Step {entry['step']:>2}: {entry['cell_id']} = {entry['verdict']:<9} "
              f"| active clues: {len(entry['active_clue_ids'])} "
              f"| revealed: {_field(clue, 'clue_id')} | SAT calls: {len(entry['sat_queries'])}")
        print(f"         queries: {queries}")
    totals = {name: sum(getattr(q.stats, name) for q in outcome.sat_queries)
              for name in ("decisions", "propagations", "backtracks", "runtime_ms")}
    print(f"Final state: {outcome.state.value} | SAT calls: {len(outcome.sat_queries)} | "
          f"decisions: {totals['decisions']} | propagations: {totals['propagations']} | "
          f"backtracks: {totals['backtracks']} | runtime: {totals['runtime_ms']:.1f} ms")


if __name__ == "__main__":
    _main()
