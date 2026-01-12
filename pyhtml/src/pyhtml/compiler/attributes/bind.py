"""Bind attribute parser ($bind)."""
from typing import Optional

from pyhtml.compiler.ast_nodes import BindAttribute, SpecialAttribute
from pyhtml.compiler.attributes.base import AttributeParser


class BindAttributeParser(AttributeParser):
    """Parses $bind attribute."""

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute is $bind."""
        return attr_name == '$bind'

    def parse(self, attr_name: str, attr_value: str, line: int, col: int) -> Optional[SpecialAttribute]:
        """Parse $bind attribute."""
        return BindAttribute(
            name=attr_name,
            value=attr_value,
            variable=attr_value,
            line=line,
            column=col
        )
