"""Private puzzle state and verdict handling for section 4.1."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from . import models
from .agent import classify

if TYPE_CHECKING:
    from .models import PublicState, Puzzle, Status, VerdictResult


def _field(record: Any, name: str) -> Any:
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


class GameEngine:
    """Reveal cards after the team agent proves their verdict from public evidence."""

    def __init__(self, puzzle: Puzzle) -> None:
        """Validate the supplied puzzle and own an independent copy of its private data."""
        models.validate_puzzle(puzzle)
        self._puzzle = deepcopy(puzzle)
        self._cards_by_id = {_field(card, "cell_id"): card for card in _field(self._puzzle, "cards")}
        self.restart()

    def get_public_state(self) -> PublicState:
        """Return an independent snapshot containing only public metadata and evidence."""
        return models.PublicState(
            schema_version=_field(self._puzzle, "schema_version"),
            puzzle_id=_field(self._puzzle, "puzzle_id"),
            grid_size=_field(self._puzzle, "grid_size"),
            revision=self._revision,
            cards=[
                models.PublicCard(cell_id=cell_id, name=_field(card, "name"),
                                  profession=_field(card, "profession"))
                for cell_id, card in self._cards_by_id.items()
            ],
            known_statuses=self._known_statuses.copy(),
            revealed_clues=deepcopy([self._revealed_clues[key] for key in sorted(self._revealed_clues)]),
        )

    def get_public_clue_owners(self) -> dict[str, str]:
        """Return the clue ID for each revealed cell for GUI presentation."""
        return {cell_id: _field(_field(self._cards_by_id[cell_id], "clue"), "clue_id")
                for cell_id in self._known_statuses}

    def submit_verdict(self, cell_id: str, status: Status) -> VerdictResult:
        """Check an unrevealed cell against public evidence and reveal it only on ACCEPTED.

        Raise ValueError for an invalid cell or status and RuntimeError if a proved
        verdict conflicts with the persisted puzzle.
        """
        if not isinstance(cell_id, str) or cell_id not in self._cards_by_id:
            raise ValueError("cell_id: expected a cell on this board")
        try:
            submitted_status = models.Status(status)
        except (TypeError, ValueError) as exc:
            raise ValueError("status: expected INNOCENT or CRIMINAL") from exc

        sat_queries = []
        newly_revealed_clue = None
        if cell_id in self._known_statuses:
            result = "ALREADY_REVEALED"
        else:
            classification_result = classify(self.get_public_state(), cell_id)
            classification = _field(classification_result, "classification")
            sat_queries = _field(classification_result, "sat_queries")
            if classification == "INCONSISTENT":
                result = "INCONSISTENT"
            elif classification == "UNKNOWN":
                result = "NOT_PROVABLE"
            elif classification not in ("INNOCENT", "CRIMINAL"):
                raise RuntimeError(f"Unsupported agent classification: {classification!r}")
            elif classification != submitted_status:
                result = "CONTRADICTED"
            else:
                card = self._cards_by_id[cell_id]
                if _field(card, "status") != submitted_status:
                    raise RuntimeError(f"Proved verdict for {cell_id} conflicts with the puzzle")
                self._reveal(cell_id)
                newly_revealed_clue = deepcopy(_field(card, "clue"))
                self._revision += 1
                result = "ACCEPTED"
        return models.VerdictResult(
            result=models.VerdictCode(result), cell_id=cell_id,
            submitted_status=submitted_status, newly_revealed_clue=newly_revealed_clue,
            public_state=self.get_public_state(), sat_queries=deepcopy(sat_queries),
        )

    def restart(self) -> PublicState:
        """Restore the initial cards and return a new public snapshot at revision zero."""
        self._known_statuses = {}
        self._revealed_clues = {}
        self._revision = 0
        for cell_id in _field(self._puzzle, "initial_revealed_cell_ids"):
            self._reveal(cell_id)
        return self.get_public_state()

    def _reveal(self, cell_id: str) -> None:
        card = self._cards_by_id[cell_id]
        clue = _field(card, "clue")
        self._known_statuses[cell_id] = models.Status(_field(card, "status"))
        self._revealed_clues[_field(clue, "clue_id")] = clue
