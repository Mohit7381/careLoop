"""OpenAI strict structured outputs reject any object schema whose `required`
does not list every property (run 20 failed on the first Analyst call:
"'required' is required to be supplied and to be an array including every key
in properties. Missing 'also_dimension'"). Optional fields must be required AND
nullable. Every schema under prompts/ is checked here before it is promoted."""
import json
from pathlib import Path

import pytest

SCHEMAS = sorted(Path("prompts").glob("*.output_schema.json"))


def _objects(node, path="$"):
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            yield path, node
        for k, v in node.items():
            yield from _objects(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _objects(v, f"{path}[{i}]")


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=[p.name for p in SCHEMAS])
def test_every_property_is_listed_in_required(schema_path):
    schema = json.loads(schema_path.read_text())
    for where, obj in _objects(schema):
        props = set(obj.get("properties") or {})
        if not props:
            continue
        missing = props - set(obj.get("required") or [])
        assert not missing, f"{schema_path.name} {where}: properties not in required: {sorted(missing)}"
        assert obj.get("additionalProperties") is False, f"{schema_path.name} {where}: additionalProperties must be false"
