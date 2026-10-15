from pathlib import Path

from api_test_agent.models import TestPlan
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.result_parser import parse_jtl
from api_test_agent.test_design import generate_plan
from api_test_agent.config import load_config


def test_parse_jtl_aggregates_repeated_labels(tmp_path: Path):
    jtl = tmp_path / "results.jtl"
    jtl.write_text(
        "timeStamp,elapsed,label,responseCode,success,failureMessage\n"
        "1,10,positive_listbooks_minimal,200,true,\n"
        "2,10,positive_listbooks_minimal,200,true,\n"
        "3,10,positive_listbooks_minimal,500,false,Server error\n",
        encoding="utf-8",
    )
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    results = parse_jtl(jtl, plan, "run-test", "local")
    record = next(r for r in results.records if r.test_id == "positive_listbooks_minimal")
    assert record.overall.value == "FAIL"
    assert record.artifact_refs.get("sample_count") == "3"
    assert record.artifact_refs.get("failure_count") == "1"
    assert results.load_stats["total_jtl_samples"] == 3
