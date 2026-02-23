import os
import tempfile
import json
import types
import sys

from plugin_loader import init_pipeline


# Create fake plugin module
def fake_upper(text: str) -> str:
    return text.upper()

def fake_strip(text: str) -> str:
    return text.strip()

fake_module = types.ModuleType("fake_plugins")
fake_module.REGISTRY = {
    "upper": fake_upper,
    "strip": fake_strip,
}

sys.modules["fake_plugins"] = fake_module


def test_pipeline_basic():
    config = {
        "module": "fake_plugins",
        "steps": ["strip", "upper"]
    }

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        json.dump(config, f)
        config_path = f.name

    pipeline = init_pipeline(config_path)
    result = pipeline("  hello world  ")

    assert result == "HELLO WORLD"

    os.remove(config_path)


if __name__ == "__main__":
    test_pipeline_basic()
    print("All tests passed.")
