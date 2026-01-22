"""Base page class with lifecycle system."""
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Any

from starlette.requests import Request
from starlette.responses import Response


class EventData(dict):
    """Dict that allows dot-access to keys for Alpine.js compatibility."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            # Check for camelCase version of name
            import re
            camel = re.sub(r'(?!^)_([a-z])', lambda x: x.group(1).upper(), name)
            if camel in self:
                return self[camel]
            raise AttributeError(f"'EventData' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        self[name] = value


class BasePage:
    """Base class for all compiled pages."""

    # Layout ID (overridden by generator)
    LAYOUT_ID: Optional[str] = None

    # Lifecycle hooks registry (extensible!)
    INIT_HOOKS = [
        'on_before_load',
        'on_load',
    ]
    
    RENDER_HOOKS = [
        'on_after_render',
    ]
    
    # Legacy support / full list
    LIFECYCLE_HOOKS = INIT_HOOKS + RENDER_HOOKS

    def __init__(self, request: Request, params: Dict[str, str], query: Dict[str, str], path: Dict[str, bool] = None, url: 'URLHelper' = None):
        self.request = request
        self.params = params or {}  # URL params from route
        self.query = query or {}  # Query string params
        self.path = path or {}
        self.url = url
        self.user = None  # Set by middleware

        # Expose params as attributes for easy access in templates
        for k, v in self.params.items():
            setattr(self, k, v)

        # Framework-managed state
        self.errors: Dict[str, str] = {}
        self.loading: Dict[str, bool] = {}
        
        # Slot registry: layout_id -> slot_name -> renderer (replacement semantics)
        self.slots: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        
        # Head slot registry: layout_id -> list of renderers (append semantics, top-down order)
        self.head_slots: Dict[str, List[Callable]] = defaultdict(list)
        
        # Async update hook for intermediate state (injected by runtime)
        self._on_update: Optional[Callable[[], Awaitable[None]]] = None

    def register_slot(self, layout_id: str, slot_name: str, renderer: Callable):
        """Register a content renderer for a slot in a specific layout."""
        self.slots[layout_id][slot_name] = renderer

    def register_head_slot(self, layout_id: str, renderer: Callable):
        """Register head content to be appended (top-down order)."""
        # Prevent duplicate registration (can happen with super()._init_slots() chaining)
        if renderer not in self.head_slots[layout_id]:
            self.head_slots[layout_id].append(renderer)

    async def render_slot(self, slot_name: str, default_renderer: Optional[Callable] = None, layout_id: str = None, append: bool = False) -> str:
        """Render a slot for the current layout."""
        target_id = layout_id or self.LAYOUT_ID
        
        # Handle $head slots with append semantics
        if append:
            parts = []
            # Render default content first (from the layout itself)
            if default_renderer:
                if asyncio.iscoroutinefunction(default_renderer):
                    parts.append(await default_renderer())
                else:
                    parts.append(default_renderer())
            
            # Collect head content from ALL layout IDs in the inheritance chain
            for layout_id_key in self.head_slots:
                for renderer in self.head_slots[layout_id_key]:
                    if asyncio.iscoroutinefunction(renderer):
                        parts.append(await renderer())
                    else:
                        parts.append(renderer())
            return ''.join(parts)
        
        # Normal replacement semantics
        if target_id and slot_name in self.slots[target_id]:
            renderer = self.slots[target_id][slot_name]
            if asyncio.iscoroutinefunction(renderer):
                return await renderer()
            return renderer()
            
        # Fallback to default content if provided
        if default_renderer:
            if asyncio.iscoroutinefunction(default_renderer):
                return await default_renderer()
            return default_renderer()
            
        return ""

    async def render(self, init: bool = True) -> Response:
        """Main render method - calls lifecycle hooks."""
        # Run init hooks only if requested (new page load)
        if init:
            for hook_name in self.INIT_HOOKS:
                if hasattr(self, hook_name):
                    hook = getattr(self, hook_name)
                    if asyncio.iscoroutinefunction(hook):
                        await hook()
                    else:
                        hook()

        # Render template (may be async for layouts with render_slot calls)
        html = await self._render_template()
        
        # Run post-render hooks (always run on render)
        for hook_name in self.RENDER_HOOKS:
            if hasattr(self, hook_name):
                hook = getattr(self, hook_name)
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()

        return Response(html, media_type='text/html')

    async def handle_event(self, event_name: str, event_data: dict) -> Response:
        """Handle client event (from @click, etc.)."""
        import inspect
        
        # Retrieve handler
        handler = getattr(self, event_name, None)
        if not handler:
            raise ValueError(f"Handler {event_name} not found")

        # Call handler
        if event_name.startswith('_handle_bind_'):
            # Binding handlers expect raw event_data
            if asyncio.iscoroutinefunction(handler):
                await handler(event_data)
            else:
                handler(event_data)
        else:
            # Regular handlers: intelligent argument mapping
            args = event_data.get('args', {})
            
            # Normalize args keys (arg-0 -> arg0) because dataset keys preserve hyphens before digits
            normalized_args = {}
            for k, v in args.items():
                if k.startswith('arg'):
                    normalized_args[k.replace('-', '')] = v
                else:
                    normalized_args[k] = v
                    
            call_kwargs = {k: v for k, v in event_data.items() if k != 'args'}
            call_kwargs.update(normalized_args)
            
            # Check signature to see what arguments the handler accepts
            sig = inspect.signature(handler)
            bound_kwargs = {}
            
            has_var_kw = False
            for param in sig.parameters.values():
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    has_var_kw = True
                    break
            
            if has_var_kw:
                # If accepts **kwargs, pass everything
                bound_kwargs = call_kwargs
            else:
                # Only pass arguments that match parameters
                for name in sig.parameters:
                    if name == 'event_data' or name == 'event':
                        bound_kwargs[name] = EventData(call_kwargs)
                    elif name in call_kwargs:
                        bound_kwargs[name] = call_kwargs[name]
            
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(**bound_kwargs)
                else:
                    handler(**bound_kwargs)
            except Exception as e:
                print(f"ERROR in handle_event for {handler_name}: {e}")
                import traceback
                traceback.print_exc()
                raise e


        # Re-render without re-initializing
        return await self.render(init=False)

    async def push_state(self):
        """Force a UI update with current state (useful for streaming progress)."""
        if self._on_update:
            if asyncio.iscoroutinefunction(self._on_update):
                await self._on_update()
            else:
                self._on_update()

    async def _render_template(self) -> str:
        """Render template - implemented by codegen."""
        return ''
