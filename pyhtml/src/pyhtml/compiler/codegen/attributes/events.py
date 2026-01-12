"""Event attribute code generator."""
from typing import Optional

import ast

from pyhtml.compiler.ast_nodes import EventAttribute
from pyhtml.compiler.codegen.attributes.base import AttributeCodegen


class EventAttributeCodegen(AttributeCodegen):
    """Generates event handler hookup for @click."""

    def generate_html(self, attr: EventAttribute) -> str:
        """Generate HTML data attribute for event."""
        # @click="handler" → data-on-click="handler"
        return f'data-on-{attr.event_type}="{attr.handler_name}"'

    def generate_handler(self, attr: EventAttribute) -> Optional[ast.FunctionDef]:
        """No extra handler needed - user defines it."""
        return None
