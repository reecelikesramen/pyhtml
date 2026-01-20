
import unittest
import asyncio
from unittest.mock import MagicMock
import sys

# Mocks
mock_starlette = MagicMock()
sys.modules['starlette'] = mock_starlette
sys.modules['starlette.requests'] = mock_starlette
sys.modules['starlette.responses'] = mock_starlette
sys.modules['starlette.routing'] = mock_starlette
sys.modules['starlette.staticfiles'] = mock_starlette
sys.modules['starlette.applications'] = mock_starlette
sys.modules['starlette.websockets'] = mock_starlette
sys.modules['starlette.datastructures'] = mock_starlette
sys.modules['starlette.types'] = mock_starlette
sys.modules['starlette.exceptions'] = mock_starlette
sys.modules['starlette.middleware'] = mock_starlette

# Mock Jinja2
mock_jinja = MagicMock()
sys.modules['jinja2'] = mock_jinja

# Mock lxml
mock_lxml = MagicMock()
sys.modules['lxml'] = mock_lxml
sys.modules['lxml.html'] = mock_lxml
sys.modules['lxml.etree'] = mock_lxml

from pyhtml.runtime.page import BasePage

class TestPageRendering(unittest.TestCase):
    def test_params_as_attributes(self):
        """Verify params are exposed as attributes."""
        request = MagicMock()
        params = {'id': '42', 'slug': 'test-post'}
        
        page = BasePage(request, params=params, query={})
        
        self.assertTrue(hasattr(page, 'id'))
        self.assertEqual(page.id, '42')
        self.assertEqual(page.slug, 'test-post')

    def test_recursive_slot_logic(self):
        """Verify slot registration logic manually."""
        # 1. Root Layout (LAYOUT_ID="ROOT")
        class RootLayout(BasePage):
            LAYOUT_ID = "ROOT"
            
            async def _render_template(self):
                # <slot /> renders default slot for layout ROOT
                renderer = self.slots.get("ROOT", {}).get("default")
                content = await renderer() if renderer else ""
                return "ROOT_START|" + content + "|ROOT_END"
                
            def _init_slots(self):
                if hasattr(super(), "_init_slots"): super()._init_slots()
                
        # 2. Sub Layout (LAYOUT_ID="SUB", parent="ROOT")
        class SubLayout(RootLayout):
            LAYOUT_ID = "SUB"
            
            # CodeGen: registers filler for ROOT default slot
            # MUST be unique to avoid override by child!
            async def _render_slot_fill_default_sub(self):
                 # SubLayout content: <slot /> (which renders SUB default slot)
                 renderer = self.slots.get("SUB", {}).get("default")
                 content = await renderer() if renderer else ""
                 return "SUB_START|" + content + "|SUB_END"
                 
            def _init_slots(self):
                if hasattr(super(), "_init_slots"): super()._init_slots()
                # Register self for parent
                self.register_slot("ROOT", "default", self._render_slot_fill_default_sub)

        # 3. Leaf Page (parent="SUB")
        class LeafPage(SubLayout):
            # NO LAYOUT_ID (it's a page)
            
            # CodeGen: registers filler for SUB default slot
            async def _render_slot_fill_default_leaf(self):
                return "LEAF_CONTENT"

            def _init_slots(self):
                if hasattr(super(), "_init_slots"): super()._init_slots()
                self.register_slot("SUB", "default", self._render_slot_fill_default_leaf)

        # Execution
        request = MagicMock()
        page = LeafPage(request, params={}, query={})
        
        # Generated code would call this in __init__
        page._init_slots()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
             # BasePage.render() calls self._render_template().
             # LeafPage inherits SubLayout (which has no _render_template in real CodeGen, 
             # wait, SubLayout DOES NOT have _render_template if generated as layout).
             # It only has slot fillers.
             # So LeafPage inherits RootLayout's _render_template!
             
             # In my mock above:
             # SubLayout DOES have _render_template defined... wait.
             # If SubLayout is generated as a LAYOUT, it SHOULD NOT have _render_template.
             # Only the ROOT has _render_template (or the one without !layout).
             
             # So I should REMOVE _render_template from SubLayout to match CodeGen behavior.
             # Actually, since I didn't define it in SubLayout above, it's already inherited.
             # So I don't need to delete anything.
             pass
             
             # But SubLayout class definition above inherits RootLayout.
             # RootLayout HAS _render_template.
             # LeafPage inherits SubLayout -> RootLayout.
             # So LeafPage has _render_template from RootLayout.
             
             content = loop.run_until_complete(page._render_template())
             self.assertEqual(content, "ROOT_START|SUB_START|LEAF_CONTENT|SUB_END|ROOT_END")
        finally:
            loop.close()

if __name__ == '__main__':
    unittest.main()
