import importlib
import json
import os
from typing import Callable, Dict, Any


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def resolve_module_name(config: Dict[str, Any]) -> str:
    return os.getenv("PLUGINS_MODULE", config.get("module", "plugins"))


def load_plugins(module_name: str) -> Dict[str, Callable[..., Any]]:
    module = importlib.import_module(module_name)
    return getattr(module, "REGISTRY")


def build_pipeline(registry: Dict[str, Callable[..., Any]], steps: list[str]) -> Callable[[str], str]:
    def pipeline(text: str) -> str:
        for step in steps:
            text = registry[step](text)
        return text
    return pipeline


def init_pipeline(config_path: str) -> Callable[[str], str]:
    config = load_config(config_path)
    module_name = resolve_module_name(config)
    registry = load_plugins(module_name)
    steps = config["steps"]
    return build_pipeline(registry, steps)
