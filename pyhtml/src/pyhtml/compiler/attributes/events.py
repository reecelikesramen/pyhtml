"""Event attribute parser."""

import re
from typing import Optional

from pyhtml.compiler.ast_nodes import EventAttribute
from pyhtml.compiler.attributes.base import AttributeParser


class EventAttributeParser(AttributeParser):
    """Parses @event attributes (click, submit, etc.)."""

    PREFIX = "@"
    PATTERN = re.compile(r"^@(\w+)$")

    def can_parse(self, attr_name: str) -> bool:
        """Check if attribute starts with @."""
        return attr_name.startswith(self.PREFIX)

    def parse(
        self, attr_name: str, attr_value: str, line: int, col: int
    ) -> Optional[EventAttribute]:
        """Parse @click.prevent.stop="handler_name" attribute."""
        # Remove @ prefix
        full_event = attr_name[1:]
        parts = full_event.split(".")
        event_type = parts[0]
        modifiers = [m for m in parts[1:] if m]

        handler_name = attr_value.strip().strip("\"'")  # Remove quotes

        # Parse handler args if present (future: handler(arg1, arg2))
        handler_args = []
        if "(" in handler_name:
            # Future: parse args
            pass

        return EventAttribute(
            name=attr_name,
            value=attr_value,
            event_type=event_type,
            handler_name=handler_name,
            modifiers=modifiers,
            args=handler_args,
            line=line,
            column=col,
        )
