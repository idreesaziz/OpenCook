from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenCook isolated RetroChimera worker")
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args()

    # RetroChimera logs its complete vocabulary while loading. Keep the JSON-lines
    # protocol quiet and reserve stderr for actionable worker failures.
    logging.disable(logging.INFO)
    from retrochimera import RetroChimeraDeNovoModel  # type: ignore[import-not-found]
    from syntheseus import Molecule  # type: ignore[import-not-found]

    kwargs = {"model_dir": str(args.model_dir)} if args.model_dir else {}
    model = RetroChimeraDeNovoModel(**kwargs)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            batches = model(
                [Molecule(request["product"])], num_results=int(request.get("limit", 5))
            )
            predictions = [
                {
                    "reactants": [{"smiles": molecule.smiles} for molecule in reaction.reactants],
                    "metadata": dict(reaction.metadata),
                }
                for reaction in batches[0]
            ]
            response: dict[str, object] = {"predictions": predictions}
        except Exception as exc:
            response = {"error": f"{type(exc).__name__}: {exc}"}
        print("OPENCOOK_RESULT " + json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
