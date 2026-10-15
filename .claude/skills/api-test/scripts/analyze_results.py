#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import click

from api_test_agent.coverage import compute_coverage
from api_test_agent.models import NormalizedResults, TestPlan
from api_test_agent.openapi_loader import load_inventory


@click.command()
@click.option("--run-dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--out", type=click.Path(path_type=Path), default=None)
def main(run_dir: Path, spec: Path, out: Path | None) -> None:
    plan = TestPlan.model_validate(
        json.loads((run_dir / "plan.copy.json").read_text(encoding="utf-8"))
    )
    results = NormalizedResults.model_validate(
        json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    )
    inventory = load_inventory(spec)
    coverage = compute_coverage(inventory, plan, results)
    payload = {
        "summary": results.summary,
        "coverage": coverage.__dict__,
    }
    text = json.dumps(payload, indent=2)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        click.echo(f"Wrote {out}")
    else:
        click.echo(text)


if __name__ == "__main__":
    main()
