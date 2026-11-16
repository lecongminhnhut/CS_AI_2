"""Launch the integrated Griductive browser game."""

import argparse
from pathlib import Path
from threading import Thread
import webbrowser


def main() -> None:
    """Check the team files, load the puzzle catalog, and open the browser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Start without opening a browser tab")
    args = parser.parse_args()

    source = Path(__file__).resolve().parent
    required = ("models", "regions", "encoder", "sat", "agent")
    missing = [f"griductive/{name}.py" for name in required
               if not (source / "griductive" / f"{name}.py").is_file()]
    puzzle_directory = source / "puzzles"
    if not any(path.is_file() for path in puzzle_directory.glob("*.json")):
        missing.append("puzzles/*.json")
    if missing:
        parser.error(f"Team integration is not ready. Missing: {', '.join(missing)}. See Source/README.md.")

    try:
        from griductive.gui.server import GriductiveServer
        from griductive.gui.team_session import load_cases

        cases = load_cases(puzzle_directory)
    except (ImportError, ValueError) as exc:
        parser.error(f"Team integration is not ready: {exc}. See Source/README.md.")

    with GriductiveServer(("127.0.0.1", args.port), cases) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Griductive is running at {url}", flush=True)
        if not args.no_browser:
            Thread(target=webbrowser.open, args=(url,), kwargs={"new": 2}, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
