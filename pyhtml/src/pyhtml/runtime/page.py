"""Base page class with lifecycle system."""
import asyncio
from typing import Dict, Optional

from starlette.requests import Request
from starlette.responses import Response


class BasePage:
    """Base class for all compiled pages."""

    # Lifecycle hooks registry (extensible!)
    LIFECYCLE_HOOKS = [
        '__before_load',
        '__on_load',
        '__after_render',
        # Future: '__on_mount', '__on_unmount', etc.
    ]

    def __init__(self, request: Request, params: Dict[str, str], query: Dict[str, str], path: Dict[str, bool] = None, url: 'URLHelper' = None):
        self.request = request
        self.params = params or {}  # URL params from route
        self.query = query or {}  # Query string params
        self.path = path or {}
        self.url = url
        self.user = None  # Set by middleware

        # Framework-managed state
        self.errors: Dict[str, str] = {}
        self.loading: Dict[str, bool] = {}

    async def render(self) -> Response:
        """Main render method - calls lifecycle hooks."""
        # Run lifecycle hooks in order
        for hook_name in self.LIFECYCLE_HOOKS:
            if hasattr(self, hook_name):
                hook = getattr(self, hook_name)
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()

        # Render template
        html = self._render_template()

        return Response(html, media_type='text/html')

    async def handle_event(self, event_name: str, event_data: dict) -> Response:
        """Handle client event (from @click, etc.)."""
        handler = getattr(self, event_name, None)
        if not handler:
            raise ValueError(f"Handler {event_name} not found")

        # Call handler with event data
        if asyncio.iscoroutinefunction(handler):
            await handler(**event_data.get('args', {}))
        else:
            handler(**event_data.get('args', {}))

        # Re-render
        return await self.render()

    def _render_template(self) -> str:
        """Render template - implemented by codegen."""
        return ''
