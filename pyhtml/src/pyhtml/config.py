"""Configuration system for PyHTML."""
import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

@dataclass
class PyHTMLConfig:
    """Project configuration."""
    pages_dir: Path = field(default_factory=lambda: Path("pages"))
    static_dir: Optional[Path] = None
    # Add other config options here as needed
    
    # Routing specific config
    trailing_slash: bool = False
    enable_pjax: bool = False
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> 'PyHTMLConfig':
        """Load configuration from pyhtml.config.py or return defaults."""
        if path is None:
            # Try to find pyhtml.config.py in current directory
            cwd = Path.cwd()
            potential_paths = [
                cwd / "pyhtml.config.py",
                cwd / "src" / "pyhtml.config.py" # In case it's in src
            ]
            for p in potential_paths:
                if p.exists():
                    path = p
                    break
        
        if path and path.exists():
            return cls._load_from_file(path)
        
        return cls()

    @classmethod
    def _load_from_file(cls, path: Path) -> 'PyHTMLConfig':
        """Load config from a specific file."""
        try:
            spec = importlib.util.spec_from_file_location("pyhtml_config", path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Check for 'config' variable
                if hasattr(module, 'config'):
                    config_obj = module.config
                    if isinstance(config_obj, cls):
                        return config_obj
                    elif isinstance(config_obj, dict):
                        # Simple dict support
                        return cls(**config_obj)
                    else:
                        print(f"WARN: 'config' in {path} must be a PyHTMLConfig instance or dict. Using defaults.")
                else:
                     print(f"WARN: No 'config' variable found in {path}. Using defaults.")
        except Exception as e:
            print(f"ERROR: Failed to load config from {path}: {e}")
            
        return cls()

# Global config instance to be populated at runtime
config = PyHTMLConfig()
