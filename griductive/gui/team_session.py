"""Adapt the team contract to the browser UI and coordinate accepted steps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .. import models
from ..agent import next_move
from ..engine import GameEngine
from ..regions import get_referenced_cell_ids


def _data(record: Any) -> dict[str, Any]:
    return asdict(record) if is_dataclass(record) else dict(record)


def load_cases(directory: Path, *, fallback_directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Validate the puzzle catalog, preferring the main directory for matching filenames."""
    paths = sorted(directory.glob("*.json"))
    if fallback_directory is not None:
        primary_names = {path.name for path in paths}
        paths.extend(path for path in sorted(fallback_directory.glob("*.json"))
                     if path.name not in primary_names)
    cases = {}
    for path in paths:
        puzzle = models.load_puzzle(path)
        data = _data(puzzle)
        puzzle_id = data["puzzle_id"]
        if puzzle_id in cases:
            raise ValueError(f"{path.name}: duplicate puzzle_id {puzzle_id!r}")
        title = puzzle_id.replace("_", " ").replace("-", " ").title()
        cases[puzzle_id] = {"id": puzzle_id, "size": data["grid_size"], "title": title, "puzzle": puzzle}
    if not cases:
        raise ValueError("Add a team-schema puzzle JSON file to Source/puzzles/.")
    return cases


def _public_clue(clue: Any, public_state: dict[str, Any]) -> dict[str, Any]:
    data = _data(clue)
    names = {card["cell_id"]: card["name"] for card in public_state["cards"]}
    kind = data["type"]
    cells = get_referenced_cell_ids(clue, public_state["grid_size"])

    def term(text: str, cell_ids: list[str]) -> dict[str, Any]:
        return {"text": text, "cells": cell_ids}

    if kind == "FACT":
        cell_id = data["cell_id"]
        parts = [term(names[cell_id], [cell_id]), {"text": " is "},
                 term(data["status"].lower(), [cell_id])]
    elif kind in ("SAME", "DIFFERENT"):
        first, second = data["cell_ids"]
        relation = "the same status" if kind == "SAME" else "different statuses"
        parts = [term(names[first], [first]), {"text": " and "}, term(names[second], [second]),
                 {"text": " have "}, term(relation, cells)]
    else:
        region = _data(data["region"])
        region_type = region["type"]
        if region_type == "EXPLICIT" and 0 < len(cells) <= 3:
            parts = []
            for index, cell in enumerate(cells):
                if index:
                    parts.append({"text": " and " if index == len(cells) - 1 else ", "})
                parts.append(term(names[cell], [cell]))
            verb = " contains " if len(cells) == 1 else " contain "
        elif region_type == "EXPLICIT":
            title = ", ".join(names[cell] for cell in cells) or "The empty group"
            parts, verb = [term(title, cells)], " contain " if len(cells) > 1 else " contains "
        else:
            if region_type == "ROW":
                title, verb = f"Row {region['row']}", " contains "
            elif region_type == "COLUMN":
                title, verb = f"Column {region['column']}", " contains "
            elif region_type == "NEIGHBORS":
                title, verb = f"The neighbors of {names[region['cell_id']]}", " contain "
            elif region_type == "CORNERS":
                title, verb = "The four corners", " contain "
            else:  # BOUNDARY, already validated by the team schema.
                title, verb = "The edge cells", " contain "
            parts = [term(title, cells)]
        count = data["k"]
        quantifier = {"EXACTLY": "exactly", "AT_LEAST": "at least", "AT_MOST": "at most"}[kind]
        noun = "criminal" if count == 1 else "criminals"
        parts.extend([{"text": verb}, term(f"{quantifier} {count} {noun}", cells)])
    parts.append({"text": "."})
    return {"id": data["clue_id"], "text": "".join(part["text"] for part in parts), "parts": parts}


class TeamSession:
    """Bridge the browser endpoints to the engine and team's public agent API."""

    def __init__(self, case: dict[str, Any]) -> None:
        """Initialize a session for one validated team puzzle."""
        self._case = case
        self.engine = GameEngine(case["puzzle"])
        self.trace_entries = []
        self._trace_modes = []
        self.query_log = []
        self._terminal = None

    def restart(self) -> None:
        """Reset the session without keeping any trace or query from its previous run."""
        self.engine.restart()
        self.trace_entries.clear()
        self._trace_modes.clear()
        self.query_log.clear()
        self._terminal = None

    def hint(self) -> dict[str, Any]:
        """Ask the team agent for a move without revealing any card."""
        public_state = self.engine.get_public_state()
        move_result = self._record_move(public_state)
        if move_result["state"] != "MOVE_AVAILABLE":
            return {"result": self._browser_result(move_result["state"])}
        return {"result": "HINT", "cell": move_result["cell_id"], "hint_scope": "ALL_REVEALED",
                "clue_cells": list(_data(public_state)["known_statuses"])}

    def step(self) -> str:
        """Ask the agent for a step, then submit its verdict through the engine."""
        public_state = self.engine.get_public_state()
        move_result = self._record_move(public_state)
        if move_result["state"] != "MOVE_AVAILABLE":
            self._terminal = self._browser_result(move_result["state"])
            return self._terminal
        return self.submit(move_result["cell_id"], move_result["verdict"], "Auto", move_result["sat_queries"])

    def submit(self, cell_id: str, status: str, mode: str = "Manual",
               move_queries: list[dict[str, Any]] | None = None) -> str:
        """Submit a verdict and write one convention-format trace entry if accepted."""
        before = _data(self.engine.get_public_state())
        verdict_result = _data(self.engine.submit_verdict(cell_id, status))
        sat_queries = [_data(query) for query in verdict_result["sat_queries"]]
        self.query_log.extend(sat_queries)
        result = verdict_result["result"]
        if result != "ACCEPTED":
            return result
        entry = {
            "puzzle_id": before["puzzle_id"], "step": len(self.trace_entries) + 1,
            "revision_before": before["revision"],
            "active_clue_ids": [clue["clue_id"] for clue in before["revealed_clues"]],
            "cell_id": cell_id, "verdict": verdict_result["submitted_status"],
            "sat_queries": (move_queries or []) + sat_queries,
            "newly_revealed_clue": _data(verdict_result["newly_revealed_clue"]),
        }
        self.trace_entries.append(entry)
        self._trace_modes.append(mode)
        after = self.engine.get_public_state()
        self._terminal = None
        if len(_data(after)["known_statuses"]) == len(before["cards"]):
            self._terminal = self._browser_result(self._record_move(after)["state"])
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return the browser view of public cards, presentation clues, and session trace."""
        snapshot = self.engine.get_public_state()
        public_state = _data(snapshot)
        statuses = public_state["known_statuses"]
        revealed = snapshot["revealed_clues"] if isinstance(snapshot, Mapping) else snapshot.revealed_clues
        source_clues = {_data(clue)["clue_id"]: clue for clue in revealed}
        owners = self.engine.get_public_clue_owners()
        clues = {cell: _public_clue(source_clues[clue_id], public_state) for cell, clue_id in owners.items()}
        cards = [
            {"cell": card["cell_id"], "name": card["name"], "profession": card["profession"],
             "status": statuses.get(card["cell_id"]), "clue": clues.get(card["cell_id"])}
            for card in public_state["cards"]
        ]
        trace = [
            {"step": entry["step"], "cell": entry["cell_id"], "verdict": entry["verdict"],
             "mode": self._trace_modes[index], "active_clues": entry["active_clue_ids"],
             "revealed": clues[entry["cell_id"]],
             "queries": [self._browser_query(query, public_state["cards"]) for query in entry["sat_queries"]]}
            for index, entry in enumerate(self.trace_entries)
        ]
        stats = {"variables": len(cards), "calls": len(self.query_log)}
        for field in ("decisions", "propagations", "backtracks", "runtime_ms"):
            stats[field] = sum(query["stats"][field] for query in self.query_log)
        return {
            "id": public_state["puzzle_id"], "title": self._case["title"], "size": public_state["grid_size"],
            "cards": cards, "opened": list(statuses), "trace": trace,
            "terminal": self._terminal, "stats": stats,
        }

    def _record_move(self, public_state: Any) -> dict[str, Any]:
        move_result = _data(next_move(public_state))
        move_result["sat_queries"] = [_data(query) for query in move_result["sat_queries"]]
        self.query_log.extend(move_result["sat_queries"])
        return move_result

    @staticmethod
    def _browser_result(state: str) -> str:
        return "UNKNOWN" if state == "STUCK" else state

    @staticmethod
    def _browser_query(query: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
        assumptions = query["assumptions"]
        literal = assumptions[0] if assumptions else None
        return {"cell": cards[abs(literal) - 1]["cell_id"] if literal else None,
                "assumed": ("CRIMINAL" if literal > 0 else "INNOCENT") if literal else None,
                "result": query["status"]}
