"""Shared schema 1.0.0 data models, enums, and puzzle validation (section 4.2)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .regions import get_all_cell_ids, parse_cell_id, resolve_region

SCHEMA_VERSION = "1.0.0"
SUPPORTED_GRID_SIZES = (3, 4, 5)


class Status(str, Enum):
    """Character verdict status."""

    INNOCENT = "INNOCENT"
    CRIMINAL = "CRIMINAL"

    def to_bool(self) -> bool:
        """Return True for CRIMINAL and False for INNOCENT."""
        return self is Status.CRIMINAL


class SatStatus(str, Enum):
    """Return status of the DPLL SAT solver."""

    SAT = "SAT"
    UNSAT = "UNSAT"


class VerdictCode(str, Enum):
    """Outcome codes returned by GameEngine.submit_verdict()."""

    ACCEPTED = "ACCEPTED"
    NOT_PROVABLE = "NOT_PROVABLE"
    CONTRADICTED = "CONTRADICTED"
    INCONSISTENT = "INCONSISTENT"
    ALREADY_REVEALED = "ALREADY_REVEALED"


class ClueType(str, Enum):
    """Supported clue templates."""

    FACT = "FACT"
    SAME = "SAME"
    DIFFERENT = "DIFFERENT"
    EXACTLY = "EXACTLY"
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"


class RegionType(str, Enum):
    """Supported region templates (4 required + 2 team extensions)."""

    ROW = "ROW"
    COLUMN = "COLUMN"
    NEIGHBORS = "NEIGHBORS"
    EXPLICIT = "EXPLICIT"
    CORNERS = "CORNERS"
    BOUNDARY = "BOUNDARY"


@dataclass
class SolverStats:
    """Counters and wall-clock runtime recorded for one SAT call."""

    decisions: int
    propagations: int
    backtracks: int
    pure_literal_assignments: int
    runtime_ms: float


@dataclass
class SatResult:
    """Result returned by griductive.sat.solve()."""

    status: SatStatus
    assignment: dict[int, bool] | None
    stats: SolverStats


@dataclass(frozen=True)
class RegionSpec:
    """Structured clue region specification."""

    type: RegionType
    row: int | None = None
    column: str | None = None
    cell_id: str | None = None
    cell_ids: list[str] | None = None


Region = RegionSpec


@dataclass(frozen=True)
class Clue:
    """Structured clue specification."""

    clue_id: str
    type: ClueType
    cell_id: str | None = None
    status: Status | None = None
    cell_ids: list[str] | None = None
    region: RegionSpec | None = None
    k: int | None = None


@dataclass(frozen=True)
class Card:
    """Complete puzzle card (private to GameEngine and puzzle files)."""

    cell_id: str
    name: str
    profession: str
    status: Status
    clue: Clue


@dataclass(frozen=True)
class Puzzle:
    """Complete Griductive puzzle matching schema 1.0.0."""

    schema_version: str
    puzzle_id: str
    grid_size: int
    cards: list[Card]
    initial_revealed_cell_ids: list[str]


@dataclass(frozen=True)
class PublicCard:
    """Public character metadata exposed in PublicState."""

    cell_id: str
    name: str
    profession: str


@dataclass(frozen=True)
class PublicState:
    """Public knowledge base snapshot exposed to agents and the GUI."""

    schema_version: str
    puzzle_id: str
    grid_size: int
    revision: int
    cards: list[PublicCard]
    known_statuses: dict[str, Status]
    revealed_clues: list[Clue]


@dataclass(frozen=True)
class VerdictResult:
    """Outcome returned when submitting a verdict to GameEngine."""

    result: VerdictCode
    cell_id: str
    submitted_status: Status
    newly_revealed_clue: Clue | None
    public_state: PublicState
    sat_queries: list[Any]


@dataclass(frozen=True)
class EncodedKB:
    """Encoded CNF knowledge base and variable/clause statistics."""

    clauses: list[list[int]]
    variable_map: dict[str, int]
    reverse_variable_map: dict[int, str]
    num_primary_variables: int
    num_auxiliary_variables: int
    num_variables: int
    num_clauses: int


def _field(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _require_nonempty_str(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: expected non-empty string, got {value!r}")
    return value


def validate_region(region: RegionSpec | Mapping[str, Any], grid_size: int) -> RegionSpec:
    """Validate a region object or mapping and normalize it into RegionSpec."""
    if not isinstance(region, (RegionSpec, Mapping)):
        raise ValueError("region: expected RegionSpec or mapping")
    raw_type = _field(region, "type")
    try:
        region_type = RegionType(raw_type)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"region.type: invalid {raw_type!r}") from exc

    resolve_region(region, grid_size)

    if region_type is RegionType.ROW:
        return RegionSpec(type=region_type, row=_field(region, "row"))
    if region_type is RegionType.COLUMN:
        return RegionSpec(type=region_type, column=_field(region, "column"))
    if region_type is RegionType.NEIGHBORS:
        return RegionSpec(type=region_type, cell_id=_field(region, "cell_id"))
    if region_type is RegionType.EXPLICIT:
        return RegionSpec(type=region_type, cell_ids=list(_field(region, "cell_ids")))
    return RegionSpec(type=region_type)


def validate_clue(clue: Clue | Mapping[str, Any], grid_size: int) -> Clue:
    """Validate a clue object or mapping and normalize it into Clue."""
    if not isinstance(clue, (Clue, Mapping)):
        raise ValueError("clue: expected Clue or mapping")
    clue_id = _require_nonempty_str(_field(clue, "clue_id"), "clue.clue_id")
    raw_type = _field(clue, "type")
    try:
        clue_type = ClueType(raw_type)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"clue.type: invalid {raw_type!r}") from exc

    if clue_type is ClueType.FACT:
        cell_id = _field(clue, "cell_id")
        parse_cell_id(cell_id, grid_size)
        raw_status = _field(clue, "status")
        try:
            status = Status(raw_status)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"clue.status: invalid {raw_status!r}") from exc
        return Clue(clue_id=clue_id, type=clue_type, cell_id=cell_id, status=status)

    if clue_type in (ClueType.SAME, ClueType.DIFFERENT):
        raw_cells = _field(clue, "cell_ids")
        if not isinstance(raw_cells, (list, tuple)) or len(raw_cells) != 2:
            raise ValueError(f"clue.cell_ids: expected 2 cell IDs for {clue_type.value}")
        c1, c2 = raw_cells
        parse_cell_id(c1, grid_size)
        parse_cell_id(c2, grid_size)
        if c1 == c2:
            raise ValueError(f"clue.cell_ids: expected 2 distinct cells, got {raw_cells!r}")
        return Clue(clue_id=clue_id, type=clue_type, cell_ids=[c1, c2])

    raw_region = _field(clue, "region")
    region = validate_region(raw_region, grid_size)
    region_cells = resolve_region(region, grid_size)
    k = _field(clue, "k")
    if isinstance(k, bool) or not isinstance(k, int) or not (0 <= k <= len(region_cells)):
        raise ValueError(
            f"clue.k: expected int in [0, {len(region_cells)}] for {clue_type.value}, got {k!r}"
        )
    return Clue(clue_id=clue_id, type=clue_type, region=region, k=k)


def validate_puzzle(puzzle: Puzzle | Mapping[str, Any]) -> Puzzle:
    """Validate a complete schema 1.0.0 puzzle and normalize it into Puzzle."""
    if not isinstance(puzzle, (Puzzle, Mapping)):
        raise ValueError("puzzle: expected Puzzle or mapping")

    schema_version = _field(puzzle, "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"schema_version: expected {SCHEMA_VERSION!r}, got {schema_version!r}")

    puzzle_id = _require_nonempty_str(_field(puzzle, "puzzle_id"), "puzzle_id")
    grid_size = _field(puzzle, "grid_size")
    if isinstance(grid_size, bool) or not isinstance(grid_size, int) or grid_size not in SUPPORTED_GRID_SIZES:
        raise ValueError(f"grid_size: expected one of {SUPPORTED_GRID_SIZES}, got {grid_size!r}")

    raw_cards = _field(puzzle, "cards")
    expected_cells = get_all_cell_ids(grid_size)
    if not isinstance(raw_cards, (list, tuple)) or len(raw_cards) != len(expected_cells):
        raise ValueError(f"cards: expected {len(expected_cells)} cards for {grid_size}x{grid_size} board")

    cards: list[Card] = []
    seen_cells: set[str] = set()
    seen_names: set[str] = set()
    seen_clue_ids: set[str] = set()

    for index, raw_card in enumerate(raw_cards):
        if not isinstance(raw_card, (Card, Mapping)):
            raise ValueError(f"cards[{index}]: expected Card or mapping")
        cell_id = _field(raw_card, "cell_id")
        parse_cell_id(cell_id, grid_size)
        if cell_id != expected_cells[index]:
            raise ValueError(
                f"cards[{index}].cell_id: expected {expected_cells[index]!r} in row-major order, got {cell_id!r}"
            )
        if cell_id in seen_cells:
            raise ValueError(f"cards[{index}].cell_id: duplicate {cell_id!r}")
        seen_cells.add(cell_id)

        name = _require_nonempty_str(_field(raw_card, "name"), f"cards[{index}].name")
        if name.lower() in seen_names:
            raise ValueError(f"cards[{index}].name: duplicate {name!r}")
        seen_names.add(name.lower())

        profession = _require_nonempty_str(_field(raw_card, "profession"), f"cards[{index}].profession")
        raw_status = _field(raw_card, "status")
        try:
            status = Status(raw_status)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cards[{index}].status: invalid {raw_status!r}") from exc

        clue = validate_clue(_field(raw_card, "clue"), grid_size)
        if clue.clue_id in seen_clue_ids:
            raise ValueError(f"cards[{index}].clue.clue_id: duplicate {clue.clue_id!r}")
        seen_clue_ids.add(clue.clue_id)

        cards.append(
            Card(cell_id=cell_id, name=name, profession=profession, status=status, clue=clue)
        )

    raw_initial = _field(puzzle, "initial_revealed_cell_ids")
    if not isinstance(raw_initial, (list, tuple)):
        raise ValueError("initial_revealed_cell_ids: expected list[str]")
    initial_revealed: list[str] = []
    seen_initial: set[str] = set()
    for cell_id in raw_initial:
        parse_cell_id(cell_id, grid_size)
        if cell_id in seen_initial:
            raise ValueError(f"initial_revealed_cell_ids: duplicate {cell_id!r}")
        seen_initial.add(cell_id)
        initial_revealed.append(cell_id)

    return Puzzle(
        schema_version=schema_version,
        puzzle_id=puzzle_id,
        grid_size=grid_size,
        cards=cards,
        initial_revealed_cell_ids=initial_revealed,
    )


def load_puzzle(path: Path | str) -> Puzzle:
    """Load, validate, and normalize a puzzle JSON file."""
    file_path = Path(path)
    try:
        raw_data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{file_path}: failed to load puzzle JSON: {exc}") from exc
    return validate_puzzle(raw_data)
