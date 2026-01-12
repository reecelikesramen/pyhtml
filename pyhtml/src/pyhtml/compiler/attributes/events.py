"""Event attribute parser."""
import re
from typing import Optional

from pyhtml.compiler.ast_nodes import EventAttribute
from pyhtml.compiler.attributes.base import AttributeParser


class EventAttributeParser(AttributeParser):
    """Parses @event attributes (click, submit, etc.)."""

    PREFIX = '@'
    PATTERN = re.compile(r'^@(\w+)$')

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute starts with @."""
        return attr_name.startswith(self.PREFIX)

    def parse(self, attr_name: str, attr_value: str, line: int, col: int) -> Optional[EventAttribute]:
        """Parse @click="handler_name" attribute."""
        match = self.PATTERN.match(attr_name)
        if not match:
            return None

        event_type = match.group(1)
        handler_name = attr_value.strip().strip('"\'')  # Remove quotes

        # Parse handler args if present (future: handler(arg1, arg2))
        handler_args = []
        if '(' in handler_name:
            # Future: parse args
            pass

        return EventAttribute(
            name=attr_name,
            value=attr_value,
            event_type=event_type,
            handler_name=handler_name,
            handler_args=handler_args,
            line=line,
            column=col
        )
