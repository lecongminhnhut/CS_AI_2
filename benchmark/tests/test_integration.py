"""Kiểm thử tích hợp theo TEAM_CONVENTIONS mục 11 (phần 4.5).

Chạy từ thư mục ``Source/``::

    python -m unittest discover -s benchmark/tests -t . -v
    # hoặc nếu đã cài pytest:  python -m pytest benchmark/tests -q

Các module của nhóm còn thiếu sẽ làm test tương ứng được SKIP (kèm lý do),
không làm hỏng các test khác.
"""

from __future__ import annotations

import csv
import importlib
import itertools
import json
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from random import Random

SOURCE_DIRECTORY = Path(__file__).resolve().parents[2]
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from benchmark import generate_puzzles, oracle  # noqa: E402

PUZZLE_PATHS = sorted((SOURCE_DIRECTORY / "puzzles").glob("*.json"))
FIXTURE_PATHS = sorted((SOURCE_DIRECTORY / "benchmark" / "fixtures").glob("*.json"))
STRESS_PATHS = sorted((SOURCE_DIRECTORY / "benchmark" / "stress").glob("*.json"))
ALL_PATHS = PUZZLE_PATHS + STRESS_PATHS + FIXTURE_PATHS
KIND_BY_ID = {puzzle_id: kind for puzzle_id, _, kind, _, _ in generate_puzzles.CATALOG}


def _module(name: str):
    try:
        return importlib.import_module(f"griductive.{name}"), None
    except Exception as exc:  # noqa: BLE001
        return None, f"griductive.{name} chưa sẵn sàng: {type(exc).__name__}: {exc}"


models, MODELS_ERROR = _module("models")
regions, REGIONS_ERROR = _module("regions")
semantics, SEMANTICS_ERROR = _module("semantics")
encoder, ENCODER_ERROR = _module("encoder")
sat, SAT_ERROR = _module("sat")
agent, AGENT_ERROR = _module("agent")
uniqueness, UNIQUENESS_ERROR = _module("uniqueness")
engine_module, ENGINE_ERROR = _module("engine")


def field_value(record, name):
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


def value_of(item):
    return getattr(item, "value", item)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def first_error(*errors):
    return next((error for error in errors if error), None)


class PuzzleSetTest(unittest.TestCase):
    """Bộ puzzle đúng loại mong đợi (chỉ dùng oracle độc lập)."""

    def test_catalog_files_exist(self):
        self.assertEqual({path.stem for path in ALL_PATHS}, set(KIND_BY_ID))

    def test_puzzles_match_expected_kind(self):
        for path in ALL_PATHS:
            with self.subTest(puzzle=path.name):
                puzzle = load_json(path)
                self.assertEqual(generate_puzzles.check(puzzle, KIND_BY_ID[puzzle["puzzle_id"]]), [])

    def test_schema_shape(self):
        for path in ALL_PATHS:
            with self.subTest(puzzle=path.name):
                puzzle = load_json(path)
                self.assertEqual(set(puzzle), {"schema_version", "puzzle_id", "grid_size", "cards",
                                               "initial_revealed_cell_ids"})
                self.assertEqual(puzzle["schema_version"], "1.0.0")
                self.assertEqual([card["cell_id"] for card in puzzle["cards"]],
                                 oracle.get_all_cell_ids(puzzle["grid_size"]))
                names = [card["name"] for card in puzzle["cards"]]
                self.assertEqual(names, sorted(names))
                clue_ids = [card["clue"]["clue_id"] for card in puzzle["cards"]]
                self.assertEqual(len(clue_ids), len(set(clue_ids)))

    def test_coverage_of_clue_and_region_types(self):
        clues = [card["clue"] for path in PUZZLE_PATHS + STRESS_PATHS for card in load_json(path)["cards"]]
        self.assertEqual({clue["type"] for clue in clues},
                         {"FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST"})
        region_types = {clue["region"]["type"] for clue in clues if "region" in clue}
        self.assertTrue({"ROW", "COLUMN", "NEIGHBORS", "EXPLICIT", "CORNERS", "BOUNDARY"} <= region_types)
        sizes = {load_json(path)["grid_size"] for path in PUZZLE_PATHS}
        self.assertTrue({3, 4} <= sizes)


@unittest.skipIf(first_error(MODELS_ERROR, REGIONS_ERROR, SEMANTICS_ERROR),
                 first_error(MODELS_ERROR, REGIONS_ERROR, SEMANTICS_ERROR))
class ModelsAndSemanticsTest(unittest.TestCase):

    def test_load_puzzle_accepts_all_files(self):
        for path in PUZZLE_PATHS + FIXTURE_PATHS:  # 5×5 chỉ khi models hỗ trợ
            with self.subTest(puzzle=path.name):
                models.load_puzzle(path)

    def test_resolve_region_matches_oracle(self):
        for grid_size in (3, 4):
            all_cell_ids = oracle.get_all_cell_ids(grid_size)
            region_list = ([{"type": "ROW", "row": row} for row in range(1, grid_size + 1)]
                           + [{"type": "COLUMN", "column": chr(65 + i)} for i in range(grid_size)]
                           + [{"type": "NEIGHBORS", "cell_id": cell} for cell in all_cell_ids]
                           + [{"type": "EXPLICIT", "cell_ids": [all_cell_ids[-1], all_cell_ids[0]]},
                              {"type": "EXPLICIT", "cell_ids": []},
                              {"type": "CORNERS"}, {"type": "BOUNDARY"}])
            for region in region_list:
                with self.subTest(grid_size=grid_size, region=region):
                    self.assertEqual(regions.resolve_region(region, grid_size),
                                     oracle.resolve_region(region, grid_size))

    def test_evaluator_matches_oracle_and_hidden_solution(self):
        for path in ALL_PATHS:
            puzzle = load_json(path)
            grid_size = puzzle["grid_size"]
            solution = {card["cell_id"]: card["status"] == "CRIMINAL" for card in puzzle["cards"]}
            rng = Random(7)
            assignments = [solution] + [{cell: rng.random() < 0.5 for cell in solution} for _ in range(30)]
            for card in puzzle["cards"]:
                for cell_assignment in assignments:
                    with self.subTest(puzzle=path.name, clue=card["clue"]["clue_id"]):
                        self.assertEqual(semantics.evaluate_clue(card["clue"], cell_assignment, grid_size),
                                         oracle.evaluate_clue(card["clue"], cell_assignment, grid_size))


@unittest.skipIf(first_error(MODELS_ERROR, SEMANTICS_ERROR, ENCODER_ERROR, SAT_ERROR),
                 first_error(MODELS_ERROR, SEMANTICS_ERROR, ENCODER_ERROR, SAT_ERROR))
class EncoderAndSatTest(unittest.TestCase):

    def test_evaluator_matches_encoder_on_3x3(self):
        """Với mọi assignment 3×3: clue đúng  <=>  CNF của clue SAT khi cố định biến chính."""
        for path in [p for p in PUZZLE_PATHS if load_json(p)["grid_size"] == 3]:
            puzzle = load_json(path)
            variable_map = encoder.build_variable_map(3)
            for card in puzzle["cards"]:
                clue = card["clue"]
                allocator = encoder.AuxiliaryVariableAllocator(10)
                clauses = encoder.encode_clue(clue, variable_map, 3, allocator)
                num_variables = allocator.next_auxiliary_var_id - 1
                for bits in itertools.product((False, True), repeat=9):
                    cell_assignment = dict(zip(oracle.get_all_cell_ids(3), bits))
                    assumptions = [variable_map[c] if v else -variable_map[c] for c, v in cell_assignment.items()]
                    sat_result = sat.solve(clauses, num_variables, assumptions)
                    expected = semantics.evaluate_clue(clue, cell_assignment, 3)
                    if (value_of(field_value(sat_result, "status")) == "SAT") != expected:
                        self.fail(f"{path.name} {clue['clue_id']} mismatch at {cell_assignment}")

    def test_variable_map_is_row_major(self):
        for grid_size in (3, 4):
            self.assertEqual(encoder.build_variable_map(grid_size),
                             {cell: index + 1 for index, cell in enumerate(oracle.get_all_cell_ids(grid_size))})

    def test_dpll_matches_brute_force(self):
        rng = Random(2024)
        for case in range(300):
            num_variables = rng.randint(1, 8)
            clauses = [[rng.choice((1, -1)) * rng.randint(1, num_variables) for _ in range(rng.randint(1, 3))]
                       for _ in range(rng.randint(0, 20))]
            expected = any(all(any((lit > 0) == bits[abs(lit) - 1] for lit in clause) for clause in clauses)
                           for bits in itertools.product((False, True), repeat=num_variables))
            sat_result = sat.solve(clauses, num_variables)
            status = value_of(field_value(sat_result, "status"))
            with self.subTest(case=case):
                self.assertEqual(status == "SAT", expected)
                assignment = field_value(sat_result, "assignment")
                stats = field_value(sat_result, "stats")
                for name in ("decisions", "propagations", "backtracks", "pure_literal_assignments", "runtime_ms"):
                    self.assertGreaterEqual(field_value(stats, name), 0)
                if expected:
                    self.assertEqual(set(assignment), set(range(1, num_variables + 1)))
                    for clause in clauses:
                        self.assertTrue(any(assignment[abs(lit)] == (lit > 0) for lit in clause))
                else:
                    self.assertIsNone(assignment)

    def test_solver_does_not_mutate_input_and_is_deterministic(self):
        clauses = [[1, 2], [-1, 3], [-2, -3]]
        snapshot = json.dumps(clauses)
        first = sat.solve(clauses, 3, [1])
        second = sat.solve(clauses, 3, [1])
        self.assertEqual(json.dumps(clauses), snapshot)
        self.assertEqual(field_value(first, "assignment"), field_value(second, "assignment"))
        for name in ("decisions", "propagations", "backtracks"):
            self.assertEqual(field_value(field_value(first, "stats"), name),
                             field_value(field_value(second, "stats"), name))
        self.assertEqual(value_of(field_value(sat.solve(clauses, 3, [1, -1]), "status")), "UNSAT")


@unittest.skipIf(first_error(MODELS_ERROR, AGENT_ERROR, ENGINE_ERROR, UNIQUENESS_ERROR),
                 first_error(MODELS_ERROR, AGENT_ERROR, ENGINE_ERROR, UNIQUENESS_ERROR))
class AgentEngineTest(unittest.TestCase):

    def _play(self, path: Path):
        """Chạy vòng suy luận; trả (state cuối, thứ tự mở, engine)."""
        engine = engine_module.GameEngine(models.load_puzzle(path))
        public_state = engine.get_public_state()
        order = []
        while True:
            move_result = agent.next_move(public_state)
            state = value_of(field_value(move_result, "state"))
            if state != "MOVE_AVAILABLE":
                return state, order, engine
            cell_id = field_value(move_result, "cell_id")
            verdict_result = engine.submit_verdict(cell_id, field_value(move_result, "verdict"))
            self.assertEqual(value_of(field_value(verdict_result, "result")), "ACCEPTED")
            public_state = field_value(verdict_result, "public_state")
            order.append(cell_id)

    def test_deduction_matches_oracle(self):
        for path in [p for p in ALL_PATHS if load_json(p)["grid_size"] <= 4]:
            with self.subTest(puzzle=path.name):
                state, order, _ = self._play(path)
                simulation = oracle.simulate_deduction(load_json(path))
                self.assertEqual(state, simulation["state"])
                self.assertEqual(order, simulation["order"])

    def test_public_state_hides_private_data(self):
        engine = engine_module.GameEngine(models.load_puzzle(PUZZLE_PATHS[0]))
        public_state = engine.get_public_state()
        cards = field_value(public_state, "cards")
        for card in cards:
            names = set(card) if isinstance(card, Mapping) else set(vars(card))
            self.assertEqual(names, {"cell_id", "name", "profession"})
        puzzle = load_json(PUZZLE_PATHS[0])
        self.assertEqual(len(field_value(public_state, "revealed_clues")),
                         len(puzzle["initial_revealed_cell_ids"]))

    def test_rejected_verdicts_keep_state(self):
        path = next(p for p in FIXTURE_PATHS if p.stem == "fixture_3x3_stuck")
        state, _, engine = self._play(path)
        self.assertEqual(state, "STUCK")
        before = engine.get_public_state()
        known = field_value(before, "known_statuses")
        unresolved = [cell for cell in oracle.get_all_cell_ids(3) if cell not in known]
        verdict_result = engine.submit_verdict(unresolved[0], "CRIMINAL")
        self.assertEqual(value_of(field_value(verdict_result, "result")), "NOT_PROVABLE")
        self.assertIsNone(field_value(verdict_result, "newly_revealed_clue"))
        after = engine.get_public_state()
        self.assertEqual(field_value(after, "revision"), field_value(before, "revision"))
        self.assertEqual(field_value(after, "known_statuses"), known)
        revealed = next(iter(known))
        already = engine.submit_verdict(revealed, value_of(known[revealed]))
        self.assertEqual(value_of(field_value(already, "result")), "ALREADY_REVEALED")
        self.assertEqual(list(field_value(already, "sat_queries")), [])

    def test_contradicted_verdict(self):
        path = PUZZLE_PATHS[0]
        engine = engine_module.GameEngine(models.load_puzzle(path))
        move_result = agent.next_move(engine.get_public_state())
        opposite = "INNOCENT" if value_of(field_value(move_result, "verdict")) == "CRIMINAL" else "CRIMINAL"
        verdict_result = engine.submit_verdict(field_value(move_result, "cell_id"), opposite)
        self.assertEqual(value_of(field_value(verdict_result, "result")), "CONTRADICTED")
        self.assertEqual(field_value(engine.get_public_state(), "revision"), 0)

    def test_restart_reproduces_initial_state(self):
        engine = engine_module.GameEngine(models.load_puzzle(PUZZLE_PATHS[0]))
        initial = json.dumps(_plain(engine.get_public_state()), sort_keys=True)
        move_result = agent.next_move(engine.get_public_state())
        engine.submit_verdict(field_value(move_result, "cell_id"), field_value(move_result, "verdict"))
        self.assertNotEqual(json.dumps(_plain(engine.get_public_state()), sort_keys=True), initial)
        self.assertEqual(json.dumps(_plain(engine.restart()), sort_keys=True), initial)

    def test_uniqueness_matches_oracle(self):
        for path in ALL_PATHS:
            puzzle = load_json(path)
            if puzzle["grid_size"] > 4:
                continue
            model_count = oracle.count_models([card["clue"] for card in puzzle["cards"]],
                                              puzzle["grid_size"], limit=2)
            expected = {0: "UNSAT", 1: "UNIQUE"}.get(model_count, "MULTIPLE")
            with self.subTest(puzzle=path.name):
                uniqueness_result = uniqueness.check_uniqueness(models.load_puzzle(path))
                self.assertEqual(value_of(field_value(uniqueness_result, "classification")), expected)


def _plain(record):
    from benchmark.run import to_jsonable
    return to_jsonable(record)


@unittest.skipIf(first_error(MODELS_ERROR, AGENT_ERROR, ENGINE_ERROR, ENCODER_ERROR),
                 first_error(MODELS_ERROR, AGENT_ERROR, ENGINE_ERROR, ENCODER_ERROR))
class RunnerSmokeTest(unittest.TestCase):

    def test_runner_writes_convention_csv(self):
        from benchmark import run
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            exit_code = run.main(["--puzzles", "puzzles/puzzle_3x3_001.json",
                                  "benchmark/fixtures/fixture_3x3_inconsistent.json",
                                  "--repeats", "1", "--output-dir", str(output_directory), "--skip-uniqueness"])
            self.assertEqual(exit_code, 0)
            with (output_directory / "results.csv").open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, run.CSV_FIELDS)
                rows = list(reader)
            self.assertEqual([row["result"] for row in rows], ["SOLVED", "INCONSISTENT"])
            trace_lines = (output_directory / "traces" / f"{rows[0]['run_id']}.jsonl").read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(trace_lines), int(rows[0]["deduction_steps"]))
            entry = json.loads(trace_lines[0])
            self.assertEqual(set(entry), {"puzzle_id", "step", "revision_before", "active_clue_ids", "cell_id",
                                          "verdict", "sat_queries", "newly_revealed_clue"})
            self.assertTrue((output_directory / "summary.md").is_file())


if __name__ == "__main__":
    unittest.main()
