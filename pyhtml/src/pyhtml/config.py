"""Configuration loader for PyHTML."""
import importlib.util
import os
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_FILENAME = "pyhtml.config.py"

def load_config(path: Path | str | None = None) -> Dict[str, Any]:
    """
    Load configuration from a python file.
    
    If path is provided, loads from there.
    Otherwise, looks for pyhtml.config.py in the current working directory.
    
    Returns a dictionary of uppercase variables found in the config module.
    """
    if path is None:
        path = Path.cwd() / DEFAULT_CONFIG_FILENAME
    else:
        path = Path(path)
        
    if not path.exists():
        return {}
        
    try:
        spec = importlib.util.spec_from_file_location("pyhtml_config", path)
        if spec is None or spec.loader is None:
            return {}
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        config = {}
        for key in dir(module):
            if key.isupper():
                config[key] = getattr(module, key)
                
        # Map config keys to CLI options
        # HOST -> host
        # PORT -> port
        # DEBUG -> reload (DEBUG=True => reload=True)
        # PAGES_DIR -> pages_dir
        # WEBTRANSPORT -> webtransport
        
        mapped_config = {}
        if "HOST" in config:
            mapped_config["host"] = config["HOST"]
        if "PORT" in config:
            mapped_config["port"] = config["PORT"]
        if "DEBUG" in config:
            mapped_config["reload"] = config["DEBUG"]
        if "PAGES_DIR" in config:
            # Handle Path objects by converting to string for CLI, or keep as Path if CLI handles it
            mapped_config["pages_dir"] = str(config["PAGES_DIR"])
        if "WEBTRANSPORT" in config:
            mapped_config["webtransport"] = config["WEBTRANSPORT"]
            
        return mapped_config
        
    except Exception as e:
        print(f"Warning: Failed to load config from {path}: {e}")
        return {}
