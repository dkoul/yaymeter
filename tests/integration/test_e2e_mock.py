import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from api_test_agent.cli import main
from click.testing import CliRunner
from api_test_agent.config import load_config
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.test_design import generate_plan, plan_to_json


class BookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/books":
            self._json(200, [{"id": 1, "title": "Test"}])
        elif self.path.startswith("/books/"):
            self._json(200, {"id": 1, "title": "Test"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return
        if "title" not in data:
            self._json(400, {"error": "missing title"})
            return
        self._json(201, {"id": 2, "title": data["title"]})


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 8765), BookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield
    server.shutdown()


def test_end_to_end_python_executor(mock_server, tmp_path):
    spec = Path("tests/fixtures/bookstore-openapi.yaml")
    config = Path("examples/test-config.yaml")
    plan_path = tmp_path / "plan.json"
    inv = load_inventory(spec)
    cfg = load_config(config)
    plan = generate_plan(inv, cfg)
    plan_path.write_text(plan_to_json(plan), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--plan",
            str(plan_path),
            "--config",
            str(config),
            "--executor",
            "python",
            "--approve",
            "--run-dir",
            str(tmp_path / "results"),
            "--run-id",
            "testrun1",
        ],
    )
    assert result.exit_code == 0, result.output
    results = json.loads((tmp_path / "results" / "testrun1" / "results.json").read_text())
    assert results["summary"].get("PASS", 0) >= 1

    report_out = tmp_path / "report.md"
    result = runner.invoke(
        main,
        [
            "report",
            "--run-dir",
            str(tmp_path / "results" / "testrun1"),
            "--spec",
            str(spec),
            "--out",
            str(report_out),
        ],
    )
    assert result.exit_code == 0
    text = report_out.read_text()
    assert "# API Test Report" in text
    assert "Coverage" in text
