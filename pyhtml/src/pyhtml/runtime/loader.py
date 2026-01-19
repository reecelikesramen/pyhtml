"""Page loader - compiles and executes .pyhtml files."""
import ast
import importlib.util
import sys
from pathlib import Path
from typing import Dict, Optional, Type

from pyhtml.compiler.codegen.generator import CodeGenerator
from pyhtml.compiler.parser import PyHTMLParser
from pyhtml.runtime.page import BasePage


class PageLoader:
    """Loads and compiles .pyhtml files into page classes."""

    def __init__(self):
        self.parser = PyHTMLParser()
        self.codegen = CodeGenerator()
        self._cache: Dict[str, Type[BasePage]] = {}  # path -> compiled class

    def load(self, pyhtml_file: Path, use_cache: bool = True) -> Type[BasePage]:
        """Load and compile a .pyhtml file into a page class."""
        # Normalize path
        pyhtml_file = pyhtml_file.resolve()
        path_key = str(pyhtml_file)
        
        # Check cache first
        if use_cache and path_key in self._cache:
            return self._cache[path_key]
        
        # Parse
        parsed = self.parser.parse_file(pyhtml_file)

        # Generate code
        module_ast = self.codegen.generate(parsed)
        ast.fix_missing_locations(module_ast)

        # Compile and load
        code = compile(module_ast, str(pyhtml_file), 'exec')
        module = type(sys)('pyhtml_page')
        
        # Inject global load_layout
        module.load_layout = self.load_layout
        
        exec(code, module.__dict__)
        
        # Find Page class (skip _LayoutBase which is imported from layout)
        for name, obj in module.__dict__.items():
            if (isinstance(obj, type) and
                issubclass(obj, BasePage) and
                obj is not BasePage and
                name != '_LayoutBase'):
                # Assign LAYOUT_ID for identification
                obj.LAYOUT_ID = str(pyhtml_file)
                # Cache the compiled class
                self._cache[path_key] = obj
                return obj
                
        raise ValueError(f"No page class found in {pyhtml_file}")

    def invalidate_cache(self, path: Path = None):
        """Clear cached classes. If path given, only clear that entry."""
        if path:
            key = str(path.resolve())
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def load_layout(self, layout_path: str, base_path: str = None) -> Type[BasePage]:
        """Load a layout file and return its class."""
        path = Path(layout_path)
        if not path.is_absolute():
            # Resolve relative to base file's directory
            if base_path:
                base_dir = Path(base_path).parent
                path = base_dir / layout_path
            else:
                # Fallback to CWD
                path = Path.cwd() / layout_path
        
        # Resolve symlinks for consistent path comparison
        path = path.resolve()
        
        return self.load(path)

# Global instance for generated code to use
_loader_instance = PageLoader()

def load_layout(path: str, base_path: str = None) -> Type[BasePage]:
    """Helper for generated code to load layouts."""
    return _loader_instance.load_layout(path, base_path)
