"""Base directive code generator."""
from abc import ABC, abstractmethod
from typing import List

import ast

from pyhtml.compiler.ast_nodes import Directive


class DirectiveCodegen(ABC):
    """Base class for directive code generation."""

    @abstractmethod
    def generate(self, directive: Directive) -> List[ast.stmt]:
        """Generate AST statements for directive."""
        pass
