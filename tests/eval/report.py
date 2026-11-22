"""Write evaluation results as Markdown, CSV and JSON."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .metrics import Score, aggregate, by_category
from .schema import RunResult


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_no data_\n"
    headers = list(rows[0])
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join("–" if row.get(h) is None else str(row.get(h)) for h in headers) + " |")
    return "\n".join(out) + "\n"


def build_markdown(scores: dict[str, list[Score]], skipped: dict[str, str], meta: dict[str, Any]) -> str:
    md = [f"# Evaluation results\n\n- Run: {meta['timestamp']}\n- Scenarios: {meta['scenario_count']}\n"]
    if skipped:
        md.append("- Skipped systems: " + "; ".join(f"`{k}` ({v})" for k, v in skipped.items()) + "\n")
    md.append("\n## Summary\n\n" + _table([aggregate(v) for v in scores.values() if v]))

    categories = sorted({c for v in scores.values() for c in by_category(v)})
    if categories:
        rows = []
        for cat in categories:
            row: dict[str, Any] = {"category": cat}
            for system, v in scores.items():
                row[system] = by_category(v).get(cat, {}).get("task_success_%")
            rows.append(row)
        md.append("\n## Task success by category (%)\n\n" + _table(rows))

    md.append("\n## Per scenario\n\n")
    rows = []
    for system, v in scores.items():
        for x in v:
            rows.append({"system": system, "scenario": x.scenario_id, "category": x.category,
                         "success": "✅" if x.task_success else "❌",
                         "calc": f"{x.calc_correct}/{x.calc_checked}", "safe": "✅" if x.safety_ok else "❌",
                         "latency_s": x.latency_s, "failures": "; ".join(x.failures)[:200] or ""})
    md.append(_table(rows))
    return "".join(md)


def write_reports(out_dir: Path, scores: dict[str, list[Score]], runs: list[RunResult],
                  skipped: dict[str, str], meta: dict[str, Any]) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"markdown": out_dir / "summary.md", "csv": out_dir / "scores.csv", "json": out_dir / "runs.json"}

    paths["markdown"].write_text(build_markdown(scores, skipped, meta), encoding="utf-8")

    flat = [asdict(x) for v in scores.values() for x in v]
    with open(paths["csv"], "w", newline="", encoding="utf-8") as f:
        if flat:
            writer = csv.DictWriter(f, fieldnames=list(flat[0]))
            writer.writeheader()
            for row in flat:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                                 for k, v in row.items()})

    paths["json"].write_text(json.dumps({"meta": meta, "skipped": skipped,
                                         "summary": [aggregate(v) for v in scores.values() if v],
                                         "runs": [asdict(r) for r in runs]},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return paths
