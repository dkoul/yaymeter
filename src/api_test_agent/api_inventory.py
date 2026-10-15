"""Helpers for working with API inventory."""

from __future__ import annotations

import json
from pathlib import Path

from api_test_agent.models import ApiInventory


def inventory_to_json(inventory: ApiInventory) -> str:
    return json.dumps(inventory.model_dump(mode="json"), indent=2, sort_keys=True)


def save_inventory(inventory: ApiInventory, path: Path | str) -> None:
    Path(path).write_text(inventory_to_json(inventory) + "\n", encoding="utf-8")


def load_inventory_json(path: Path | str) -> ApiInventory:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ApiInventory.model_validate(data)
