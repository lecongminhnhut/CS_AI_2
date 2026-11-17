"""Deterministic DPLL SAT solver for the Griductive schema 1.0.0 contract."""

from time import perf_counter

from .models import SatResult, SatStatus, SolverStats


def solve(
    clauses: list[list[int]],
    num_variables: int,
    assumptions: list[int] | None = None,
) -> SatResult:
    """Solve a CNF with temporary assumptions and statistics for this call only.

    Args:
        clauses: CNF as lists of signed, nonzero integer variable IDs.
        num_variables: Total number of primary and auxiliary variables.
        assumptions: Optional literals required to hold in this call.

    Returns:
        A SatResult with SAT and a complete assignment for IDs 1..num_variables,
        or UNSAT and assignment=None. Unassigned variables are filled with False
        without increasing any counter. No input list is modified.

    Raises:
        ValueError: An input has the wrong type or an invalid literal. The
            message identifies its location. Booleans are not accepted as ints.
    """
    started_at = perf_counter()
    normalized_clauses = _validate_and_normalize(clauses, num_variables, assumptions)
    stats = SolverStats(
        decisions=0,
        propagations=0,
        backtracks=0,
        pure_literal_assignments=0,
        runtime_ms=0.0,
    )

    if assumptions is not None:
        normalized_clauses.extend([literal] for literal in assumptions)
    assignment = _dpll(normalized_clauses, {}, num_variables, stats)
    if assignment is not None:
        for var_id in range(1, num_variables + 1):
            assignment.setdefault(var_id, False)

    sat_result = SatResult(
        status=SatStatus.SAT if assignment is not None else SatStatus.UNSAT,
        assignment=assignment,
        stats=stats,
    )
    stats.runtime_ms = (perf_counter() - started_at) * 1000.0
    return sat_result


def _validate_and_normalize(
    clauses: list[list[int]],
    num_variables: int,
    assumptions: list[int] | None,
) -> list[list[int]]:
    """Validate every input location and return a normalized CNF copy."""
    if (not isinstance(num_variables, int) or isinstance(num_variables, bool)
            or num_variables < 0):
        raise ValueError("num_variables: expected a nonnegative int, not bool")
    if not isinstance(clauses, list):
        raise ValueError("clauses: expected list[list[int]]")
    if assumptions is not None and not isinstance(assumptions, list):
        raise ValueError("assumptions: expected None or list[int]")

    normalized_clauses = []
    for clause_index, clause in enumerate(clauses):
        if not isinstance(clause, list):
            raise ValueError(f"clauses[{clause_index}]: expected list[int]")
        for literal_index, literal in enumerate(clause):
            _validate_literal(
                literal, num_variables, f"clauses[{clause_index}][{literal_index}]"
            )

        literals = list(dict.fromkeys(clause))
        literal_set = set(literals)
        if not any(-literal in literal_set for literal in literals):
            normalized_clauses.append(literals)

    if assumptions is not None:
        for index, literal in enumerate(assumptions):
            _validate_literal(literal, num_variables, f"assumptions[{index}]")
    return normalized_clauses


def _validate_literal(literal: int, num_variables: int, location: str) -> None:
    """Raise ValueError with a field path for a literal outside the contract."""
    if (not isinstance(literal, int) or isinstance(literal, bool)
            or literal == 0 or abs(literal) > num_variables):
        raise ValueError(
            f"{location}: expected a nonzero int with abs(literal) in "
            f"1..{num_variables}, not bool"
        )


def _simplify_clauses(clauses: list[list[int]], literal: int) -> list[list[int]]:
    """Return a CNF copy after setting literal true, preserving empty clauses."""
    return [
        [remaining for remaining in clause if remaining != -literal]
        for clause in clauses
        if literal not in clause
    ]


def _unit_propagate(
    clauses: list[list[int]],
    assignment: dict[int, bool],
    stats: SolverStats,
) -> tuple[list[list[int]], dict[int, bool], bool]:
    """Propagate ordered units into the branch's assignment until stable/conflict."""
    while True:
        if any(not clause for clause in clauses):
            return clauses, assignment, True

        unit_literal = min(
            (clause[0] for clause in clauses if len(clause) == 1),
            key=lambda literal: (abs(literal), literal),
            default=None,
        )
        if unit_literal is None:
            return clauses, assignment, False

        var_id = abs(unit_literal)
        value = unit_literal > 0
        if var_id in assignment:
            if assignment[var_id] != value:
                return clauses, assignment, True
        else:
            assignment[var_id] = value
            stats.propagations += 1
        clauses = _simplify_clauses(clauses, unit_literal)


def _select_variable(assignment: dict[int, bool], num_variables: int) -> int:
    """Return the smallest unassigned ID; called only for an unresolved CNF."""
    return next(
        var_id for var_id in range(1, num_variables + 1) if var_id not in assignment
    )


def _dpll(
    clauses: list[list[int]],
    assignment: dict[int, bool],
    num_variables: int,
    stats: SolverStats,
) -> dict[int, bool] | None:
    """Search one branch, sharing counters but keeping assignments branch-local."""
    simplified_clauses, assignment, has_conflict = _unit_propagate(
        clauses, assignment, stats
    )
    if has_conflict:
        return None
    if not simplified_clauses:
        return assignment

    selected_var_id = _select_variable(assignment, num_variables)
    for branch_value in (True, False):
        stats.decisions += 1
        branch_assignment = assignment.copy()
        branch_assignment[selected_var_id] = branch_value
        literal = selected_var_id if branch_value else -selected_var_id
        branch_clauses = _simplify_clauses(simplified_clauses, literal)
        result = _dpll(branch_clauses, branch_assignment, num_variables, stats)
        if result is not None:
            return result
        stats.backtracks += 1
    return None
