"""Evaluation runner: Agent vs. Baseline (vs. reference oracle) on the scenario catalogue.

Usage (from the repository root):
    python tests/run_evaluation.py                          # agent + baseline (skips missing ones)
    python tests/run_evaluation.py --systems reference      # self-test of the runner (should be 100%)
    python tests/run_evaluation.py --scenarios S02,S07,S22 --systems agent
    python tests/run_evaluation.py --list                   # print the scenario catalogue

Results are written to tests/results/<timestamp>/ (summary.md, scores.csv, runs.json).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow `python tests/run_evaluation.py`
    sys.path.insert(0, str(ROOT))

from tests.eval.metrics import Score, aggregate, score  # noqa: E402
from tests.eval.report import write_reports  # noqa: E402
from tests.eval.schema import RunResult  # noqa: E402
from tests.eval.systems import REGISTRY, SystemUnavailable  # noqa: E402
from tests.scenarios.catalog import SCENARIOS  # noqa: E402


def run(system_names: list[str], scenario_ids: list[str] | None = None, out_root: Path | None = None,
        timestamp: str | None = None) -> dict:
    scenarios = [s for s in SCENARIOS if not scenario_ids or s.id in scenario_ids]
    if scenario_ids and (unknown := set(scenario_ids) - {s.id for s in scenarios}):
        raise SystemExit(f"Unknown scenario id(s): {sorted(unknown)}")

    systems, skipped = [], {}
    for name in system_names:
        if name not in REGISTRY:
            raise SystemExit(f"Unknown system {name!r}; choose from {sorted(REGISTRY)}")
        try:
            systems.append(REGISTRY[name]())
        except SystemUnavailable as exc:
            skipped[name] = str(exc)

    scores: dict[str, list[Score]] = {}
    runs: list[RunResult] = []
    for system in systems:
        scores[system.name] = []
        for s in scenarios:
            if not system.applies_to(s):
                continue
            result = system.run(s)
            runs.append(result)
            scores[system.name].append(score(s, result))
            mark = "✓" if scores[system.name][-1].task_success else "✗"
            print(f"  [{system.name}] {s.id} {mark} {s.title}")

    timestamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    meta = {"timestamp": timestamp, "scenario_count": len(scenarios), "systems": [s.name for s in systems]}
    paths = write_reports((out_root or ROOT / "tests" / "results") / timestamp, scores, runs, skipped, meta)
    return {"scores": scores, "skipped": skipped, "paths": paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--systems", default="agent,baseline", help="comma separated: agent, baseline, reference")
    parser.add_argument("--scenarios", default="", help="comma separated scenario ids (default: all)")
    parser.add_argument("--out", default="", help="output root directory (default tests/results)")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args()

    if args.list:
        for s in SCENARIOS:
            print(f"{s.id}  {s.category:<22} {s.expected.outcome:<22} {s.title}")
        return

    result = run([x.strip() for x in args.systems.split(",") if x.strip()],
                 [x.strip() for x in args.scenarios.split(",") if x.strip()] or None,
                 Path(args.out) if args.out else None)
    for name, reason in result["skipped"].items():
        print(f"! skipped {name}: {reason}")
    for name, v in result["scores"].items():
        print(aggregate(v))
    if not result["scores"]:
        print("No system could be run. Use --systems reference to self-test the runner.")
    print(f"Report: {result['paths']['markdown']}")


if __name__ == "__main__":
    main()
