#!/usr/bin/env python3
"""Generate JMX from plan JSON without executing."""
import json
import sys
from pathlib import Path

import click

from api_test_agent.jmx_builder import write_jmx
from api_test_agent.models import TestPlan


@click.command()
@click.option("--plan", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--profile", default="functional")
def main(plan: Path, out: Path, profile: str) -> None:
    model = TestPlan.model_validate(json.loads(plan.read_text(encoding="utf-8")))
    write_jmx(model, out, profile=profile)
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    main()
