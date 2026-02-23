import os
import tempfile
import json
import types
import sys

from plugin_loader import init_pipeline


# --- Create a fake plugin module dynamically ---
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
    # Create temporary config file
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
    
    
    import importlib
    import functools
    import json
    import os
    from pathlib import Path
    from typing import Callable, Dict, Any, Iterable, List, Tuple
    
    
    class PluginLoaderError(Exception):
        """Base exception for plugin loader errors."""
    
    
    class ConfigError(PluginLoaderError):
        """Raised when configuration is missing or invalid."""
    
    
    class RegistryError(PluginLoaderError):
        """Raised when plugin registry cannot be loaded or is invalid."""
    
    
    class PipelineError(PluginLoaderError):
        """Raised when pipeline construction or execution fails."""
    
    
    def load_config(path: str) -> Dict[str, Any]:
        """Load a JSON configuration file and return it as a dictionary.
    
        Args:
            path: Path to the JSON configuration file.
    
        Returns:
            The parsed configuration dictionary.
    
        Raises:
            ConfigError: If the file can't be read or JSON is invalid.
        """
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            with p.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in config {path}: {exc}") from exc
    
        if not isinstance(cfg, dict):
            raise ConfigError(f"Config {path} must be a JSON object at top level")
    
        return cfg
    
    
    def resolve_module_name(config: Dict[str, Any]) -> str:
        """Resolve the plugins module name.
    
        Priority: environment variable `PLUGINS_MODULE` overrides config key `module`.
        Defaults to "plugins" when neither is provided.
        """
        env = os.getenv("PLUGINS_MODULE")
        if env:
            return env
        module_name = config.get("module") if isinstance(config, dict) else None
        return module_name or "plugins"
    
    
    def _validate_registry(registry: Dict[str, Callable[..., Any]]) -> None:
        if not isinstance(registry, dict):
            raise RegistryError("Registry must be a dict of name->callable")
        for name, fn in registry.items():
            if not isinstance(name, str):
                raise RegistryError(f"Registry key is not str: {name!r}")
            if not callable(fn):
                raise RegistryError(f"Registry entry for '{name}' is not callable")
    
    
    def _validate_steps_list(steps: Any) -> List[str]:
        """Validate that `steps` is a non-empty list of non-empty strings.
    
        Returns the validated list of step names.
        Raises ConfigError on invalid input.
        """
        if not isinstance(steps, list):
            raise ConfigError("Config 'steps' must be a list of plugin names")
        if not steps:
            raise ConfigError("Config 'steps' must not be empty")
        validated: List[str] = []
        for i, s in enumerate(steps):
            if not isinstance(s, str) or not s:
                raise ConfigError(f"Config 'steps' contains invalid entry at index {i}: {s!r}")
            validated.append(s)
        return validated
    
    
    @functools.lru_cache(maxsize=32)
    def load_plugins(module_name: str) -> Dict[str, Callable[..., Any]]:
        """Import a module and return a plugins registry.
    
        The loader looks for the following in order on the imported module:
        - a top-level `REGISTRY` object (dict or callable returning dict)
        - a callable `get_registry()` which returns the dict
    
        Raises RegistryError when the module cannot be imported or the
        registry doesn't conform to the expected shape.
        """
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise RegistryError(f"Plugin module not found: {module_name}") from exc
    
        # Prefer an explicit REGISTRY attribute. It may be a dict or a callable
        # factory returning a dict.
        if hasattr(module, "REGISTRY"):
            reg = getattr(module, "REGISTRY")
            if callable(reg):
                try:
                    reg = reg()
                except Exception as exc:
                    raise RegistryError(f"Calling REGISTRY factory in module '{module_name}' failed: {exc}") from exc
        elif hasattr(module, "get_registry") and callable(getattr(module, "get_registry")):
            try:
                reg = getattr(module, "get_registry")()
            except Exception as exc:
                raise RegistryError(f"Calling get_registry() in module '{module_name}' failed: {exc}") from exc
        else:
            raise RegistryError(f"Plugin module '{module_name}' does not expose REGISTRY or get_registry()")
    
        _validate_registry(reg)
        return reg
    
    
    def build_pipeline(registry: Dict[str, Callable[..., Any]], steps: Iterable[str]) -> Callable[[Any], Any]:
        """Build a pipeline function that applies named plugins in order.
    
        Args:
            registry: A mapping of plugin name -> callable.
            steps: An iterable of plugin names to apply in order.
    
        Returns:
            A callable that accepts one argument (input) and returns the transformed output.
    
        Raises:
            PipelineError: If any step name is missing from the registry.
        """
        step_list: List[str] = list(steps)
    
        # Ensure step names are strings
        for i, s in enumerate(step_list):
            if not isinstance(s, str) or not s:
                raise PipelineError(f"Invalid step name at index {i}: {s!r}")
    
        # Validate steps exist in registry. Using local vars to reduce attribute lookups.
        missing = [s for s in step_list if s not in registry]
        if missing:
            available = list(registry.keys())[:20]
            raise PipelineError(f"Unknown pipeline steps: {missing}. Available: {available}")
    
        # Pre-resolve callables to avoid dict lookups during pipeline execution.
        callables: List[Callable[[Any], Any]] = [registry[s] for s in step_list]
    
        def pipeline(data: Any) -> Any:
            value = data
            for idx, fn in enumerate(callables):
                try:
                    value = fn(value)
                except Exception as exc:
                    # Provide the step name in the error using step_list
                    raise PipelineError(f"Error in step '{step_list[idx]}': {exc}") from exc
            return value
    
        return pipeline
    
    
    def init_pipeline(config_path: str) -> Callable[[Any], Any]:
        """Initialize a processing pipeline from a JSON configuration file.
    
        Config format example:
        {
            "module": "my_plugins",
            "steps": ["strip", "lowercase", "tokenize"]
        }
    
        The `module` key is optional and can be overridden by the
        `PLUGINS_MODULE` environment variable.
        """
        config = load_config(config_path)
        if "steps" not in config:
            raise ConfigError("Config must include a top-level 'steps' list")
        steps = _validate_steps_list(config["steps"])
    
        module_name = resolve_module_name(config)
        registry = load_plugins(module_name)
    
        # Cache built pipelines keyed by (module_name, tuple(steps)). This avoids
        # rebuilding the same pipeline repeatedly when init_pipeline is called
        # multiple times with identical configs. We keep a small in-module cache
        # as the registry objects are typically stable for a module.
        if not hasattr(init_pipeline, "_pipeline_cache"):
            init_pipeline._pipeline_cache = {}  # type: ignore[attr-defined]
    
        key: Tuple[str, Tuple[str, ...]] = (module_name, tuple(steps))
        cache = init_pipeline._pipeline_cache  # type: ignore[attr-defined]
        if key in cache:
            return cache[key]
    
        pipeline = build_pipeline(registry, steps)
        cache[key] = pipeline
        return pipeline
    
    
    __all__ = [
        "load_config",
        "resolve_module_name",
        "load_plugins",
        "build_pipeline",
        "init_pipeline",
        "PluginLoaderError",
        "ConfigError",
        "RegistryError",
        "PipelineError",
    ]   
    
    import importlib
    import importlib
    import functools
    import json
    import os
    from pathlib import Path
    from typing import Callable, Dict, Any, Iterable, List, Tuple
    
    
    class PluginLoaderError(Exception):
        """Base exception for plugin loader errors."""
    
    
    class ConfigError(PluginLoaderError):
        """Raised when configuration is missing or invalid."""
    
    
    class RegistryError(PluginLoaderError):
        """Raised when plugin registry cannot be loaded or is invalid."""
    
    
    class PipelineError(PluginLoaderError):
        """Raised when pipeline construction or execution fails."""
    
    
    def load_config(path: str) -> Dict[str, Any]:
        """Load a JSON configuration file and return it as a dictionary.
    
        Args:
            path: Path to the JSON configuration file.
    
        Returns:
            The parsed configuration dictionary.
    
        Raises:
            ConfigError: If the file can't be read or JSON is invalid.
        """
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            with p.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in config {path}: {exc}") from exc
    
        if not isinstance(cfg, dict):
            raise ConfigError(f"Config {path} must be a JSON object at top level")
    
        return cfg
    
    
    def resolve_module_name(config: Dict[str, Any]) -> str:
        """Resolve the plugins module name.
    
        Priority: environment variable `PLUGINS_MODULE` overrides config key `module`.
        Defaults to "plugins" when neither is provided.
        """
        env = os.getenv("PLUGINS_MODULE")
        if env:
            return env
        module_name = config.get("module") if isinstance(config, dict) else None
        return module_name or "plugins"
    
    
    def _validate_registry(registry: Dict[str, Callable[..., Any]]) -> None:
        if not isinstance(registry, dict):
            raise RegistryError("Registry must be a dict of name->callable")
        for name, fn in registry.items():
            if not isinstance(name, str):
                raise RegistryError(f"Registry key is not str: {name!r}")
            if not callable(fn):
                raise RegistryError(f"Registry entry for '{name}' is not callable")
    
    
    def _validate_steps_list(steps: Any) -> List[str]:
        """Validate that `steps` is a non-empty list of non-empty strings.
    
        Returns the validated list of step names.
        Raises ConfigError on invalid input.
        """
        if not isinstance(steps, list):
            raise ConfigError("Config 'steps' must be a list of plugin names")
        if not steps:
            raise ConfigError("Config 'steps' must not be empty")
        validated: List[str] = []
        for i, s in enumerate(steps):
            if not isinstance(s, str) or not s:
                raise ConfigError(f"Config 'steps' contains invalid entry at index {i}: {s!r}")
            validated.append(s)
        return validated
    
    
    @functools.lru_cache(maxsize=32)
    def load_plugins(module_name: str) -> Dict[str, Callable[..., Any]]:
        """Import a module and return a plugins registry.
    
        The loader looks for the following in order on the imported module:
        - a top-level `REGISTRY` object (dict or callable returning dict)
        - a callable `get_registry()` which returns the dict
    
        Raises RegistryError when the module cannot be imported or the
        registry doesn't conform to the expected shape.
        """
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise RegistryError(f"Plugin module not found: {module_name}") from exc
    
        # Prefer an explicit REGISTRY attribute. It may be a dict or a callable
        # factory returning a dict.
        if hasattr(module, "REGISTRY"):
            reg = getattr(module, "REGISTRY")
            if callable(reg):
                try:
                    reg = reg()
                except Exception as exc:
                    raise RegistryError(f"Calling REGISTRY factory in module '{module_name}' failed: {exc}") from exc
        elif hasattr(module, "get_registry") and callable(getattr(module, "get_registry")):
            try:
                reg = getattr(module, "get_registry")()
            except Exception as exc:
                raise RegistryError(f"Calling get_registry() in module '{module_name}' failed: {exc}") from exc
        else:
            raise RegistryError(f"Plugin module '{module_name}' does not expose REGISTRY or get_registry()")
    
        _validate_registry(reg)
        return reg
    
    
    def build_pipeline(registry: Dict[str, Callable[..., Any]], steps: Iterable[str]) -> Callable[[Any], Any]:
        """Build a pipeline function that applies named plugins in order.
    
        Args:
            registry: A mapping of plugin name -> callable.
            steps: An iterable of plugin names to apply in order.
    
        Returns:
            A callable that accepts one argument (input) and returns the transformed output.
    
        Raises:
            PipelineError: If any step name is missing from the registry.
        """
        step_list: List[str] = list(steps)
    
        # Ensure step names are strings
        for i, s in enumerate(step_list):
            if not isinstance(s, str) or not s:
                raise PipelineError(f"Invalid step name at index {i}: {s!r}")
    
        # Validate steps exist in registry. Using local vars to reduce attribute lookups.
        missing = [s for s in step_list if s not in registry]
        if missing:
            available = list(registry.keys())[:20]
            raise PipelineError(f"Unknown pipeline steps: {missing}. Available: {available}")
    
        # Pre-resolve callables to avoid dict lookups during pipeline execution.
        callables: List[Callable[[Any], Any]] = [registry[s] for s in step_list]
    
        def pipeline(data: Any) -> Any:
            value = data
            for idx, fn in enumerate(callables):
                try:
                    value = fn(value)
                except Exception as exc:
                    # Provide the step name in the error using step_list
                    raise PipelineError(f"Error in step '{step_list[idx]}': {exc}") from exc
            return value
    
        return pipeline
    
    
    def init_pipeline(config_path: str) -> Callable[[Any], Any]:
        """Initialize a processing pipeline from a JSON configuration file.
    
        Config format example:
        {
            "module": "my_plugins",
            "steps": ["strip", "lowercase", "tokenize"]
        }
    
        The `module` key is optional and can be overridden by the
        `PLUGINS_MODULE` environment variable.
        """
        config = load_config(config_path)
        if "steps" not in config:
            raise ConfigError("Config must include a top-level 'steps' list")
        steps = _validate_steps_list(config["steps"])
    
        module_name = resolve_module_name(config)
        registry = load_plugins(module_name)
    
        # Cache built pipelines keyed by (module_name, tuple(steps)). This avoids
        # rebuilding the same pipeline repeatedly when init_pipeline is called
        # multiple times with identical configs. We keep a small in-module cache
        # as the registry objects are typically stable for a module.
        if not hasattr(init_pipeline, "_pipeline_cache"):
            init_pipeline._pipeline_cache = {}  # type: ignore[attr-defined]
    
        key: Tuple[str, Tuple[str, ...]] = (module_name, tuple(steps))
        cache = init_pipeline._pipeline_cache  # type: ignore[attr-defined]
        if key in cache:
            return cache[key]
    
        pipeline = build_pipeline(registry, steps)
        cache[key] = pipeline
        return pipeline
    
    
    __all__ = [
        "load_config",
        "resolve_module_name",
        "load_plugins",
        "build_pipeline",
        "init_pipeline",
        "PluginLoaderError",
        "ConfigError",
        "RegistryError",
        "PipelineError",
    ]


    import functools
    import json
    import os
    from pathlib import Path
    from typing import Callable, Dict, Any, Iterable, List, Tuple
    
    
    class PluginLoaderError(Exception):
        """Base exception for plugin loader errors."""
    
    
    class ConfigError(PluginLoaderError):
        """Raised when configuration is missing or invalid."""
    
    
    class RegistryError(PluginLoaderError):
        """Raised when plugin registry cannot be loaded or is invalid."""
    
    
    class PipelineError(PluginLoaderError):
        """Raised when pipeline construction or execution fails."""
    
    
    def load_config(path: str) -> Dict[str, Any]:
        """Load a JSON configuration file and return it as a dictionary.
    
        Args:
            path: Path to the JSON configuration file.
    
        Returns:
            The parsed configuration dictionary.
    
        Raises:
            ConfigError: If the file can't be read or JSON is invalid.
        """
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            with p.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in config {path}: {exc}") from exc
    
        if not isinstance(cfg, dict):
            raise ConfigError(f"Config {path} must be a JSON object at top level")
    
        return cfg
    
    
    def resolve_module_name(config: Dict[str, Any]) -> str:
        """Resolve the plugins module name.
    
        Priority: environment variable `PLUGINS_MODULE` overrides config key `module`.
        Defaults to "plugins" when neither is provided.
        """
        env = os.getenv("PLUGINS_MODULE")
        if env:
            return env
        module_name = config.get("module") if isinstance(config, dict) else None
        return module_name or "plugins"
    
    
    def _validate_registry(registry: Dict[str, Callable[..., Any]]) -> None:
        if not isinstance(registry, dict):
            raise RegistryError("Registry must be a dict of name->callable")
        for name, fn in registry.items():
            if not isinstance(name, str):
                raise RegistryError(f"Registry key is not str: {name!r}")
            if not callable(fn):
                raise RegistryError(f"Registry entry for '{name}' is not callable")
    
    
    def _validate_steps_list(steps: Any) -> List[str]:
        """Validate that `steps` is a non-empty list of non-empty strings.
    
        Returns the validated list of step names.
        Raises ConfigError on invalid input.
        """
        if not isinstance(steps, list):
            raise ConfigError("Config 'steps' must be a list of plugin names")
        if not steps:
            raise ConfigError("Config 'steps' must not be empty")
        validated: List[str] = []
        for i, s in enumerate(steps):
            if not isinstance(s, str) or not s:
                raise ConfigError(f"Config 'steps' contains invalid entry at index {i}: {s!r}")
            validated.append(s)
        return validated
    
    
    @functools.lru_cache(maxsize=32)
    def load_plugins(module_name: str) -> Dict[str, Callable[..., Any]]:
        """Import a module and return a plugins registry.
    
        The loader looks for the following in order on the imported module:
        - a top-level `REGISTRY` object (dict or callable returning dict)
        - a callable `get_registry()` which returns the dict
    
        Raises RegistryError when the module cannot be imported or the
        registry doesn't conform to the expected shape.
        """
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise RegistryError(f"Plugin module not found: {module_name}") from exc
    
        # Prefer an explicit REGISTRY attribute. It may be a dict or a callable
        # factory returning a dict.
        if hasattr(module, "REGISTRY"):
            reg = getattr(module, "REGISTRY")
            if callable(reg):
                try:
                    reg = reg()
                except Exception as exc:
                    raise RegistryError(f"Calling REGISTRY factory in module '{module_name}' failed: {exc}") from exc
        elif hasattr(module, "get_registry") and callable(getattr(module, "get_registry")):
            try:
                reg = getattr(module, "get_registry")()
            except Exception as exc:
                raise RegistryError(f"Calling get_registry() in module '{module_name}' failed: {exc}") from exc
        else:
            raise RegistryError(f"Plugin module '{module_name}' does not expose REGISTRY or get_registry()")
    
        _validate_registry(reg)
        return reg
    
    
    def build_pipeline(registry: Dict[str, Callable[..., Any]], steps: Iterable[str]) -> Callable[[Any], Any]:
        """Build a pipeline function that applies named plugins in order.
    
        Args:
            registry: A mapping of plugin name -> callable.
            steps: An iterable of plugin names to apply in order.
    
        Returns:
            A callable that accepts one argument (input) and returns the transformed output.
    
        Raises:
            PipelineError: If any step name is missing from the registry.
        """
        step_list: List[str] = list(steps)
    
        # Ensure step names are strings
        for i, s in enumerate(step_list):
            if not isinstance(s, str) or not s:
                raise PipelineError(f"Invalid step name at index {i}: {s!r}")
    
        # Validate steps exist in registry. Using local vars to reduce attribute lookups.
        missing = [s for s in step_list if s not in registry]
        if missing:
            available = list(registry.keys())[:20]
            raise PipelineError(f"Unknown pipeline steps: {missing}. Available: {available}")
    
        # Pre-resolve callables to avoid dict lookups during pipeline execution.
        callables: List[Callable[[Any], Any]] = [registry[s] for s in step_list]
    
        def pipeline(data: Any) -> Any:
            value = data
            for idx, fn in enumerate(callables):
                try:
                    value = fn(value)
                except Exception as exc:
                    # Provide the step name in the error using step_list
                    raise PipelineError(f"Error in step '{step_list[idx]}': {exc}") from exc
            return value
    
        return pipeline
    
    
    def init_pipeline(config_path: str) -> Callable[[Any], Any]:
        """Initialize a processing pipeline from a JSON configuration file.
    
        Config format example:
        {
            "module": "my_plugins",
            "steps": ["strip", "lowercase", "tokenize"]
        }
    
        The `module` key is optional and can be overridden by the
        `PLUGINS_MODULE` environment variable.
        """
        config = load_config(config_path)
        if "steps" not in config:
            raise ConfigError("Config must include a top-level 'steps' list")
        steps = _validate_steps_list(config["steps"])
    
        module_name = resolve_module_name(config)
        registry = load_plugins(module_name)
    
        # Cache built pipelines keyed by (module_name, tuple(steps)). This avoids
        # rebuilding the same pipeline repeatedly when init_pipeline is called
        # multiple times with identical configs. We keep a small in-module cache
        # as the registry objects are typically stable for a module.
        if not hasattr(init_pipeline, "_pipeline_cache"):
            init_pipeline._pipeline_cache = {}  # type: ignore[attr-defined]
    
        key: Tuple[str, Tuple[str, ...]] = (module_name, tuple(steps))
        cache = init_pipeline._pipeline_cache  # type: ignore[attr-defined]
        if key in cache:
            return cache[key]
    
        pipeline = build_pipeline(registry, steps)
        cache[key] = pipeline
        return pipeline
    
    
    __all__ = [
        "load_config",
        "resolve_module_name",
        "load_plugins",
        "build_pipeline",
        "init_pipeline",
        "PluginLoaderError",
        "ConfigError",
        "RegistryError",
        "PipelineError",
    ]
