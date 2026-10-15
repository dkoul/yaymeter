"""CLI entry point."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import click

from api_test_agent import __version__
from api_test_agent.api_inventory import inventory_to_json
from api_test_agent.config import load_config
from api_test_agent.coverage import compute_coverage
from api_test_agent.jmeter_runner import JMeterNotFoundError, find_jmeter, jmeter_version, run_jmeter
from api_test_agent.jmx_builder import write_jmx
from api_test_agent.models import RunManifest, TestPlan, utc_now_iso
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.python_executor import execute_plan
from api_test_agent.report import render_report, write_report
from api_test_agent.result_parser import parse_jtl
from api_test_agent.safety import validate_plan_for_run
from api_test_agent.test_design import generate_plan, plan_to_json, validate_plan


@click.group()
@click.version_option(__version__, prog_name="api-test-agent")
def main() -> None:
    """OpenAPI-driven API testing with JMeter or Python executor."""


@main.command("check-environment")
def check_environment() -> None:
    """Print Python and JMeter availability."""
    click.echo(f"Python: {sys.version.split()[0]}")
    jm = find_jmeter()
    if jm:
        click.echo(f"JMeter: {jm} (version {jmeter_version(jm)})")
    else:
        click.echo("JMeter: not found (use --executor python for local runs)")


@main.command("inspect")
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--out", type=click.Path(path_type=Path), default=None, help="Write inventory JSON")
def inspect_cmd(spec: Path, out: Path | None) -> None:
    """Validate spec and print operation inventory."""
    inventory = load_inventory(spec)
    text = inventory_to_json(inventory)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        click.echo(f"Wrote inventory to {out}")
    else:
        click.echo(text)


@main.command("plan")
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--config", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path))
def plan_cmd(spec: Path, config: Path, out: Path) -> None:
    """Generate deterministic test plan JSON."""
    inventory = load_inventory(spec)
    cfg = load_config(config)
    plan = generate_plan(inventory, cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(plan_to_json(plan) + "\n", encoding="utf-8")
    click.echo(f"Wrote {len(plan.test_cases)} test cases to {out}")


@main.command("validate-plan")
@click.option("--plan", required=True, type=click.Path(exists=True, path_type=Path))
def validate_plan_cmd(plan: Path) -> None:
    """Validate test plan schema and invariants."""
    data = json.loads(plan.read_text(encoding="utf-8"))
    model = TestPlan.model_validate(data)
    errors = validate_plan(model)
    if errors:
        for e in errors:
            click.echo(f"ERROR: {e}", err=True)
        raise SystemExit(1)
    click.echo("Plan is valid.")


@main.command("run")
@click.option("--plan", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--config", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--profile",
    type=click.Choice(["functional", "performance"]),
    default="functional",
)
@click.option("--approve", is_flag=True, help="Approve mutations or performance tests")
@click.option(
    "--executor",
    type=click.Choice(["jmeter", "python"]),
    default="jmeter",
    help="jmeter (default) or python (no JMeter required)",
)
@click.option("--run-dir", type=click.Path(path_type=Path), default=Path("results"))
@click.option("--run-id", default=None, help="Optional run id")
def run_cmd(
    plan: Path,
    config: Path,
    profile: str,
    approve: bool,
    executor: str,
    run_dir: Path,
    run_id: str | None,
) -> None:
    """Execute an existing plan (does not regenerate tests)."""
    cfg = load_config(config)
    model = TestPlan.model_validate(json.loads(plan.read_text(encoding="utf-8")))
    validate_plan_for_run(model, cfg, profile, approve)

    run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
    gen_dir = Path("generated-tests") / run_id
    gen_dir.mkdir(parents=True, exist_ok=True)
    jmx_path = gen_dir / "plan.jmx"
    write_jmx(model, jmx_path, profile=profile)

    out_run = Path(run_dir) / run_id
    out_run.mkdir(parents=True, exist_ok=True)
    (out_run / "plan.copy.json").write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")

    manifest = RunManifest(
        run_id=run_id,
        spec_hash=model.spec_hash,
        config_hash=model.config_hash,
        seed=model.seed,
        generator_version=model.generator_version,
        python_version=sys.version.split()[0],
        jmeter_version=jmeter_version(),
        profile=profile,
        started_at=utc_now_iso(),
        base_url=model.base_url,
        target_label=cfg.target_label,
        approvals={"mutations": approve, "performance": approve},
        artifacts={"jmx": str(jmx_path)},
    )

    if executor == "python":
        results = execute_plan(model, cfg, out_run, run_id, cfg.target_label)
        manifest.artifacts["results_json"] = str(out_run / "results.json")
    else:
        try:
            jtl, log, jm_manifest = run_jmeter(
                jmx_path,
                Path(run_dir),
                run_id=run_id,
                timeout_seconds=cfg.safety.run_timeout_seconds,
            )
            manifest.artifacts.update(jm_manifest.artifacts)
            manifest.jmeter_version = jm_manifest.jmeter_version
            if not jtl.exists():
                click.echo("JMeter did not produce JTL; check logs.", err=True)
                raise SystemExit(2)
            results = parse_jtl(jtl, model, run_id, cfg.target_label)
            (out_run / "results.json").write_text(
                results.model_dump_json(indent=2), encoding="utf-8"
            )
        except JMeterNotFoundError as e:
            click.echo(str(e), err=True)
            raise SystemExit(2) from e

    manifest.finished_at = utc_now_iso()
    (out_run / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    click.echo(f"Run complete: {out_run}")
    click.echo(f"Summary: {results.summary}")


@main.command("report")
@click.option("--run-dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--spec", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--out", type=click.Path(path_type=Path), default=None)
def report_cmd(run_dir: Path, spec: Path | None, out: Path | None) -> None:
    """Generate Markdown report from a run directory."""
    plan_path = run_dir / "plan.copy.json"
    if not plan_path.exists():
        raise click.ClickException(f"Missing {plan_path}")
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise click.ClickException(f"Missing {results_path}")

    plan = TestPlan.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
    from api_test_agent.models import NormalizedResults

    results = NormalizedResults.model_validate(json.loads(results_path.read_text(encoding="utf-8")))
    manifest_path = run_dir / "manifest.json"
    manifest = None
    if manifest_path.exists():
        manifest = RunManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))

    if spec:
        inventory = load_inventory(spec)
    else:
        from api_test_agent.models import ApiInventory, OperationModel

        inventory = ApiInventory(
            openapi_version="3.0.0",
            spec_hash=plan.spec_hash,
            operations=[
                OperationModel(operation_id=t.operation_id, method="GET", path="/")
                for t in plan.test_cases
            ],
        )

    coverage = compute_coverage(inventory, plan, results)
    md = render_report(plan, results, coverage, manifest)
    out_path = out or Path("reports") / f"{run_dir.name}.md"
    write_report(md, out_path)
    click.echo(f"Wrote report to {out_path}")


if __name__ == "__main__":
    main()
