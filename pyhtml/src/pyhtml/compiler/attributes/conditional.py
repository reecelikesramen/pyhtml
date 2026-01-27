"""Conditional attribute parsers ($if, $show)."""

from typing import Optional

from pyhtml.compiler.ast_nodes import IfAttribute, ShowAttribute, SpecialAttribute
from pyhtml.compiler.attributes.base import AttributeParser
from pyhtml.compiler.exceptions import PyHTMLSyntaxError


class ConditionalAttributeParser(AttributeParser):
    """Parses $if and $show attributes."""

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute is $if or $show."""
        return attr_name in ("$if", "$show")

    def parse(
        self, attr_name: str, attr_value: str, line: int, col: int
    ) -> Optional[SpecialAttribute]:
        """Parse conditional attribute."""
        if not (attr_value.startswith("{") and attr_value.endswith("}")):
            raise PyHTMLSyntaxError(
                f"Value for '{attr_name}' must be wrapped in brackets: {attr_name}={{expr}}",
                line=line,
            )
        
        expr = attr_value[1:-1].strip()

        if attr_name == "$if":
            return IfAttribute(
                name=attr_name, value=attr_value, condition=expr, line=line, column=col
            )
        elif attr_name == "$show":
            return ShowAttribute(
                name=attr_name, value=attr_value, condition=expr, line=line, column=col
            )
        return None
