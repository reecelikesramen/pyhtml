"""Loop attribute parsers ($for, $key)."""
from typing import Optional

from pyhtml.compiler.ast_nodes import ForAttribute, KeyAttribute, SpecialAttribute
from pyhtml.compiler.attributes.base import AttributeParser


class LoopAttributeParser(AttributeParser):
    """Parses $for attributes."""

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute is $for."""
        return attr_name == '$for'

    def parse(self, attr_name: str, attr_value: str, line: int, col: int) -> Optional[SpecialAttribute]:
        """Parse $for attribute."""
        # Parse "item in items" or "key, value in items"
        parts = attr_value.split(' in ', 1)
        if len(parts) != 2:
            # We don't raise error here, just return nothing or let it be handled as valid attribute?
            # Ideally validation happens here.
            # But creating AST node blindly is safer if we want to defer errors.
            # But "item in items" is pretty fundamental.
            raise ValueError(f"Invalid $for syntax at line {line}: '{attr_value}'. Expected 'item in items'.")
        
        loop_vars = parts[0].strip()
        iterable = parts[1].strip()
        
        return ForAttribute(
            name=attr_name,
            value=attr_value,
            is_template_tag=False, # Populated later
            loop_vars=loop_vars,
            iterable=iterable,
            line=line,
            column=col
        )


class KeyAttributeParser(AttributeParser):
    """Parses $key attributes."""

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute is $key."""
        return attr_name == '$key'

    def parse(self, attr_name: str, attr_value: str, line: int, col: int) -> Optional[SpecialAttribute]:
        """Parse $key attribute."""
        return KeyAttribute(
            name=attr_name,
            value=attr_value,
            expr=attr_value,
            line=line,
            column=col
        )
