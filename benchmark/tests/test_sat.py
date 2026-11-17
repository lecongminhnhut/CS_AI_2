"""Public-API tests for the schema 1.0.0 DPLL solver.

With real models, run from the repository root:
    python -m unittest discover -s benchmark/tests -p test_sat.py -v

Only while griductive.models is absent, run in a separate test process:
    python -m benchmark.tests.test_sat --stub-models

The explicit stub mode installs exactly the three solver contract types in
memory. Normal unittest discovery never installs stubs or hides import errors.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib
import importlib.util
from itertools import product
import math
import random
import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any
import unittest

if TYPE_CHECKING:
    from griductive.models import SatResult

sat: ModuleType


def setUpModule() -> None:
    """Load the actual solver; missing real models fail normal test discovery."""
    global sat
    sat = importlib.import_module("griductive.sat")


def _counters(sat_result: SatResult) -> tuple[int, int, int, int]:
    """Return deterministic counters, excluding wall-clock runtime."""
    stats = sat_result.stats
    return (stats.decisions, stats.propagations, stats.backtracks,
            stats.pure_literal_assignments)


def _satisfies(
    assignment: dict[int, bool],
    clauses: list[list[int]],
    assumptions: list[int],
) -> bool:
    """Evaluate original CNF and assumptions directly, without normalization."""
    return (
        all(any(assignment[abs(literal)] == (literal > 0) for literal in clause)
            for clause in clauses)
        and all(assignment[abs(literal)] == (literal > 0) for literal in assumptions)
    )


def _brute_force(
    clauses: list[list[int]], num_variables: int, assumptions: list[int]
) -> bool:
    """Return satisfiability by exhaustive enumeration for small test inputs."""
    for values in product((False, True), repeat=num_variables):
        assignment = dict(enumerate(values, start=1))
        if _satisfies(assignment, clauses, assumptions):
            return True
    return False


class SatTests(unittest.TestCase):
    """Check solver behavior through solve, including deterministic statistics."""

    def assert_sat(
        self,
        clauses: list[list[int]],
        num_variables: int,
        assumptions: list[int] | None = None,
    ) -> SatResult:
        """Require a complete Boolean model satisfying the original inputs."""
        sat_result = sat.solve(clauses, num_variables, assumptions)
        self.assertIsInstance(sat_result, sat.SatResult)
        self.assertIs(sat_result.status, sat.SatStatus.SAT)
        self.assertIsInstance(sat_result.assignment, dict)
        assignment = sat_result.assignment
        self.assertEqual(set(assignment), set(range(1, num_variables + 1)))
        self.assertTrue(all(type(var_id) is int for var_id in assignment))
        self.assertTrue(all(type(value) is bool for value in assignment.values()))
        self.assertTrue(_satisfies(assignment, clauses, assumptions or []))
        self.assert_stats(sat_result)
        return sat_result

    def assert_unsat(
        self,
        clauses: list[list[int]],
        num_variables: int,
        assumptions: list[int] | None = None,
    ) -> SatResult:
        """Require UNSAT with None rather than an empty assignment."""
        sat_result = sat.solve(clauses, num_variables, assumptions)
        self.assertIsInstance(sat_result, sat.SatResult)
        self.assertIs(sat_result.status, sat.SatStatus.UNSAT)
        self.assertIsNone(sat_result.assignment)
        self.assert_stats(sat_result)
        return sat_result

    def assert_stats(self, sat_result: SatResult) -> None:
        """Require every statistics field and valid runtime without timing limits."""
        self.assertIsInstance(sat_result.stats, sat.SolverStats)
        for counter in _counters(sat_result):
            self.assertIs(type(counter), int)
            self.assertGreaterEqual(counter, 0)
        self.assertEqual(sat_result.stats.pure_literal_assignments, 0)
        self.assertIsInstance(sat_result.stats.runtime_ms, float)
        self.assertTrue(math.isfinite(sat_result.stats.runtime_ms))
        self.assertGreaterEqual(sat_result.stats.runtime_ms, 0.0)

    def test_empty_cnf_with_zero_variables(self) -> None:
        sat_result = self.assert_sat([], 0)
        self.assertEqual(sat_result.assignment, {})
        self.assertEqual(_counters(sat_result), (0, 0, 0, 0))

    def test_empty_cnf_fills_free_variables_false(self) -> None:
        sat_result = self.assert_sat([], 4)
        self.assertEqual(sat_result.assignment, {1: False, 2: False, 3: False, 4: False})
        self.assertEqual(_counters(sat_result), (0, 0, 0, 0))

    def test_empty_clause_conflicts_at_root(self) -> None:
        for clauses, num_variables in (([[]], 0), ([[]], 3), ([[1], []], 1)):
            with self.subTest(clauses=clauses, num_variables=num_variables):
                sat_result = self.assert_unsat(clauses, num_variables)
                self.assertEqual(_counters(sat_result), (0, 0, 0, 0))

    def test_multi_step_unit_propagation(self) -> None:
        sat_result = self.assert_sat([[1], [-1, 2], [-2, 3], [-3, -4]], 5)
        self.assertEqual(sat_result.assignment,
                         {1: True, 2: True, 3: True, 4: False, 5: False})
        self.assertEqual(_counters(sat_result), (0, 4, 0, 0))

    def test_conflicting_units(self) -> None:
        for clauses in ([[1], [-1]], [[-1], [1]], [[1, 1], [-1, -1]]):
            with self.subTest(clauses=clauses):
                sat_result = self.assert_unsat(clauses, 1)
                self.assertEqual(_counters(sat_result), (0, 1, 0, 0))

    def test_units_prioritize_smallest_variable(self) -> None:
        sat_result = self.assert_unsat([[4], [3], [1], [-1, 2], [-2]], 4)
        self.assertEqual(_counters(sat_result), (0, 2, 0, 0))

    def test_new_units_reenter_priority_order(self) -> None:
        # -2 creates -1, then -3; all must precede the original unit 3.
        sat_result = self.assert_unsat([[3], [-3, 1], [-1, 2], [-2]], 3)
        self.assertEqual(_counters(sat_result), (0, 3, 0, 0))

    def test_duplicate_literals_create_one_unit_assignment(self) -> None:
        sat_result = self.assert_sat([[1, 1], [-1, 2, 2]], 2)
        self.assertEqual(sat_result.assignment, {1: True, 2: True})
        self.assertEqual(_counters(sat_result), (0, 2, 0, 0))

    def test_tautologies_are_removed_before_search(self) -> None:
        sat_result = self.assert_sat([[1, -1, 1], [-2, 2], [3, -3]], 4)
        self.assertEqual(sat_result.assignment, {1: False, 2: False, 3: False, 4: False})
        self.assertEqual(_counters(sat_result), (0, 0, 0, 0))

    def test_duplicate_clauses_do_not_repeat_propagations(self) -> None:
        sat_result = self.assert_sat([[1], [1], [-1, 2], [-1, 2]], 2)
        self.assertEqual(_counters(sat_result), (0, 2, 0, 0))

    def test_auxiliary_and_absent_variables_receive_assignments(self) -> None:
        # IDs 1..2 are primary; 3..6 are auxiliary, with no special treatment.
        sat_result = self.assert_sat([[1], [-1, 5], [-5, -6]], 6, [-3])
        self.assertEqual(sat_result.assignment,
                         {1: True, 2: False, 3: False, 4: False, 5: True, 6: False})
        self.assertEqual(_counters(sat_result), (0, 4, 0, 0))

    def test_smallest_unused_id_is_selected_even_if_absent_from_cnf(self) -> None:
        sat_result = self.assert_sat([[3, 4]], 4)
        self.assertEqual(sat_result.assignment, {1: True, 2: True, 3: True, 4: False})
        self.assertEqual(_counters(sat_result), (3, 0, 0, 0))

    def test_true_branch_first_without_pure_literal_elimination(self) -> None:
        sat_result = self.assert_sat([[1, 2], [-1, 2]], 2)
        self.assertEqual(sat_result.assignment, {1: True, 2: True})
        self.assertEqual(_counters(sat_result), (1, 1, 0, 0))

    def test_reference_backtracking_counts_and_rollback(self) -> None:
        sat_result = self.assert_sat([[-1, 2], [-1, -2], [1, 2]], 2)
        self.assertEqual(sat_result.assignment, {1: False, 2: True})
        self.assertEqual(_counters(sat_result), (2, 2, 1, 0))

    def test_unsat_counts_both_failed_branches(self) -> None:
        sat_result = self.assert_unsat([[1, 2], [1, -2], [-1, 2], [-1, -2]], 2)
        self.assertEqual(_counters(sat_result), (2, 2, 2, 0))

    def test_nested_backtracking_retains_failed_work(self) -> None:
        clauses = [[1, 2], [1, -2], [-1, 2], [-1, -2]]
        # Gate an UNSAT two-variable CNF behind 1=True; only 1=False works.
        gated = [[-1] + [(abs(literal) + 1) * (1 if literal > 0 else -1)
                           for literal in clause] for clause in clauses]
        sat_result = self.assert_sat(gated, 3)
        self.assertEqual(sat_result.assignment, {1: False, 2: False, 3: False})
        self.assertEqual(_counters(sat_result), (4, 2, 3, 0))

    def test_duplicate_assumptions_and_cnf_units_count_once(self) -> None:
        sat_result = self.assert_sat([[1], [-1, 2]], 3, [1, 1, 2, -3, -3])
        self.assertEqual(sat_result.assignment, {1: True, 2: True, 3: False})
        self.assertEqual(_counters(sat_result), (0, 3, 0, 0))

    def test_opposite_assumptions_are_valid_unsat(self) -> None:
        for assumptions in ([1, -1], [-1, 1], [1, 1, -1]):
            with self.subTest(assumptions=assumptions):
                sat_result = self.assert_unsat([], 1, assumptions)
                self.assertEqual(_counters(sat_result), (0, 1, 0, 0))

    def test_assumptions_conflicting_with_cnf(self) -> None:
        sat_result = self.assert_unsat([[1]], 1, [-1])
        self.assertEqual(_counters(sat_result), (0, 1, 0, 0))
        chained = self.assert_unsat([[-1, 2], [-2, 3]], 3, [1, -3])
        self.assertEqual(_counters(chained), (0, 3, 0, 0))

    def test_assumptions_are_propagated_on_empty_cnf(self) -> None:
        sat_result = self.assert_sat([], 3, [-2, 3])
        self.assertEqual(sat_result.assignment, {1: False, 2: False, 3: True})
        self.assertEqual(_counters(sat_result), (0, 2, 0, 0))

    def test_calls_with_different_assumptions_are_independent(self) -> None:
        clauses = [[1, 2]]
        first = self.assert_sat(clauses, 2, [-1])
        second = self.assert_sat(clauses, 2, [-2])
        self.assert_unsat(clauses, 2, [-1, -2])
        third = self.assert_sat(clauses, 2)
        self.assertEqual(first.assignment, {1: False, 2: True})
        self.assertEqual(second.assignment, {1: True, 2: False})
        self.assertEqual(third.assignment, {1: True, 2: False})
        self.assertEqual(_counters(third), (1, 0, 0, 0))
        self.assertEqual(_counters(self.assert_sat(clauses, 2, [])), _counters(third))
        self.assertIsNot(first.stats, second.stats)
        self.assertIsNot(second.stats, third.stats)
        first.assignment[1] = True
        first.stats.decisions = 999
        self.assertEqual(second.assignment, {1: True, 2: False})
        self.assertEqual(_counters(self.assert_sat(clauses, 2, [-1])), (0, 2, 0, 0))

    def test_inputs_are_unchanged_for_sat_and_unsat(self) -> None:
        for assumptions in ([], [-1], [1, -1], [-1, -2]):
            with self.subTest(assumptions=assumptions):
                shared_clause = [1, 1, 2]
                clauses = [shared_clause, [2, -2], shared_clause]
                clauses_before = deepcopy(clauses)
                clause_ids = [id(clause) for clause in clauses]
                assumptions_before = assumptions.copy()
                sat.solve(clauses, 2, assumptions)
                self.assertEqual(clauses, clauses_before)
                self.assertEqual([id(clause) for clause in clauses], clause_ids)
                self.assertIs(clauses[0], shared_clause)
                self.assertIs(clauses[2], shared_clause)
                self.assertEqual(assumptions, assumptions_before)

    def test_invalid_inputs_report_location_and_preserve_inputs(self) -> None:
        cases: list[tuple[Any, Any, Any, str]] = [
            *[([], value, None, "num_variables")
              for value in (-1, True, False, 1.0, "1", None)],
            *[(value, 1, None, "clauses") for value in (None, (), {}, "1", 1)],
            *[([value], 1, None, "clauses[0]")
              for value in (None, (1,), {1}, "1", 1)],
            *[([[value]], 1, None, "clauses[0][0]")
              for value in (True, False, 0, 2, -2, 1.0, "1", None, [1])],
            *[([], 1, value, "assumptions")
              for value in ((), {}, "1", 1, True)],
            *[([], 1, [value], "assumptions[0]")
              for value in (True, False, 0, 2, -2, 1.0, "1", None, [1])],
            ([[1]], 0, None, "clauses[0][0]"),
            ([], 0, [-1], "assumptions[0]"),
            ([[], [1, -1, 0]], 1, None, "clauses[1][2]"),
            ([[1, -1, True]], 1, None, "clauses[0][2]"),
            ([[1, -1, 2]], 1, None, "clauses[0][2]"),
            ([[1, -1], [0]], 1, None, "clauses[1][0]"),
            ([[], (1,)], 1, None, "clauses[1]"),
            ([[]], 1, [1, 0], "assumptions[1]"),
            ([[1, -1]], 1, [False], "assumptions[0]"),
            ([], 1, [1, -1, 0], "assumptions[2]"),
        ]
        for clauses, num_variables, assumptions, location in cases:
            with self.subTest(clauses=clauses, num_variables=num_variables,
                              assumptions=assumptions):
                clauses_before = deepcopy(clauses)
                assumptions_before = deepcopy(assumptions)
                clause_ids = ([id(clause) for clause in clauses]
                              if isinstance(clauses, list) else None)
                with self.assertRaises(ValueError) as context:
                    sat.solve(clauses, num_variables, assumptions)
                self.assertTrue(str(context.exception).startswith(location + ":"),
                                str(context.exception))
                self.assertEqual(clauses, clauses_before)
                self.assertEqual(assumptions, assumptions_before)
                if clause_ids is not None:
                    self.assertEqual([id(clause) for clause in clauses], clause_ids)

    def test_repeated_inputs_have_identical_models_and_counters(self) -> None:
        for clauses, assumptions in (([[-1, 2], [-1, -2], [1, 2]], []),
                                     ([[1, 2], [1, -2], [-1, 2], [-1, -2]], []),
                                     ([], [-2, 3]), ([], [])):
            with self.subTest(clauses=clauses, assumptions=assumptions):
                first = sat.solve(clauses, 4, assumptions)
                for _ in range(5):
                    repeated = sat.solve(clauses, 4, assumptions)
                    self.assertIs(repeated.status, first.status)
                    self.assertEqual(repeated.assignment, first.assignment)
                    self.assertEqual(_counters(repeated), _counters(first))
                    self.assertIsNot(repeated.stats, first.stats)

    def test_concurrent_calls_are_independent(self) -> None:
        clauses = [[-1, 2], [-1, -2], [1, 2]]
        assumptions_list = [None, [1], [-1], [2], [-2], [1, -1]] * 8
        expected = [sat.solve(clauses, 3, assumptions) for assumptions in assumptions_list]
        with ThreadPoolExecutor(max_workers=4) as executor:
            actual = list(executor.map(
                lambda assumptions: sat.solve(clauses, 3, assumptions), assumptions_list
            ))
        self.assertEqual(len({id(result.stats) for result in actual}), len(actual))
        for result, reference in zip(actual, expected):
            self.assertIs(result.status, reference.status)
            self.assertEqual(result.assignment, reference.assignment)
            self.assertEqual(_counters(result), _counters(reference))

    def test_small_seeded_cnfs_match_brute_force(self) -> None:
        generator = random.Random(42)
        for num_variables in range(6):
            literals = [literal for var_id in range(1, num_variables + 1)
                        for literal in (var_id, -var_id)]
            for case_index in range(150):
                clauses = []
                for _ in range(generator.randrange(9)):
                    length = (generator.randrange(5) if case_index % 4 == 0
                              else generator.randint(1, 4))
                    clauses.append([generator.choice(literals) for _ in range(length)]
                                   if literals else [])
                assumptions = ([generator.choice(literals)
                                for _ in range(generator.randrange(5))] if literals else [])
                with self.subTest(num_variables=num_variables, case_index=case_index):
                    expected_sat = _brute_force(clauses, num_variables, assumptions)
                    if expected_sat:
                        self.assert_sat(clauses, num_variables, assumptions)
                    else:
                        self.assert_unsat(clauses, num_variables, assumptions)


def _install_model_stubs() -> None:
    """Install three contract types only for the explicitly requested CLI process."""
    from dataclasses import dataclass
    from enum import Enum

    if importlib.util.find_spec("griductive.models") is not None:
        raise RuntimeError("Real griductive.models exists; run normal unittest discovery")

    class SatStatus(str, Enum):
        SAT = "SAT"
        UNSAT = "UNSAT"

    @dataclass
    class SolverStats:
        decisions: int
        propagations: int
        backtracks: int
        pure_literal_assignments: int
        runtime_ms: float

    @dataclass
    class SatResult:
        status: SatStatus
        assignment: dict[int, bool] | None
        stats: SolverStats

    stub_models = ModuleType("griductive.models")
    stub_models.SatStatus = SatStatus
    stub_models.SolverStats = SolverStats
    stub_models.SatResult = SatResult
    sys.modules["griductive.models"] = stub_models
    print("STUB MODE: algorithm/contract tests only; real models integration unverified.",
          file=sys.stderr)


if __name__ == "__main__":
    if "--stub-models" in sys.argv:
        sys.argv.remove("--stub-models")
        _install_model_stubs()
    unittest.main(verbosity=2)
