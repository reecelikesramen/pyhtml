"""Bind attribute parser ($bind)."""

from typing import Optional

from pyhtml.compiler.ast_nodes import BindAttribute, SpecialAttribute
from pyhtml.compiler.attributes.base import AttributeParser


class BindAttributeParser(AttributeParser):
    """Parses $bind attribute."""

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute is $bind or $bind:busy."""
        return attr_name == "$bind" or attr_name.startswith("$bind:")

    def parse(
        self, attr_name: str, attr_value: str, line: int, col: int
    ) -> Optional[SpecialAttribute]:
        """Parse $bind attribute."""
        binding_type = None
        if ":" in attr_name:
            binding_type = attr_name.split(":", 1)[1]

        return BindAttribute(
            name=attr_name,
            value=attr_value,
            variable=attr_value,
            binding_type=binding_type,
            line=line,
            column=col,
        )
