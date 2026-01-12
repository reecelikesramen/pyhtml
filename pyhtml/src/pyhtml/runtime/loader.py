"""Page loader - compiles and executes .pyhtml files."""
import ast
import importlib.util
import sys
from pathlib import Path
from typing import Optional, Type

from pyhtml.compiler.codegen.generator import CodeGenerator
from pyhtml.compiler.parser import PyHTMLParser
from pyhtml.runtime.page import BasePage


class PageLoader:
    """Loads and compiles .pyhtml files into page classes."""

    def __init__(self):
        self.parser = PyHTMLParser()
        self.codegen = CodeGenerator()

    def load(self, pyhtml_file: Path) -> Type[BasePage]:
        """Load and compile a .pyhtml file into a page class."""
        # Parse
        parsed = self.parser.parse_file(pyhtml_file)

        # Generate code
        module_ast = self.codegen.generate(parsed)
        ast.fix_missing_locations(module_ast)

        # Compile to code object
        code = compile(module_ast, str(pyhtml_file), 'exec')

        # Create module
        module_name = f'_pyhtml_{pyhtml_file.stem}_{id(pyhtml_file)}'
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        # Execute in module namespace
        exec(code, module.__dict__)

        # Find page class
        for name, obj in module.__dict__.items():
            if (isinstance(obj, type) and
                issubclass(obj, BasePage) and
                obj is not BasePage):
                print(f"DEBUG: Found page class {name}")
                print(f"DEBUG: Attributes: {dir(obj)}")
                return obj

        raise ValueError(f"No page class found in {pyhtml_file}")
