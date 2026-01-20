
import unittest
import tempfile
import shutil
import sys
from unittest.mock import MagicMock

# Mock starlette
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

# Mock jinja2
mock_jinja2 = MagicMock()
sys.modules['jinja2'] = mock_jinja2

# Mock lxml (parser uses it)
mock_lxml = MagicMock()
sys.modules['lxml'] = mock_lxml
sys.modules['lxml.html'] = mock_lxml
sys.modules['lxml.etree'] = mock_lxml

from pathlib import Path
from pyhtml.runtime.app import PyHTML
from pyhtml.runtime.router import Router

# Mock base page for loader
class MockPage:
    LAYOUT_ID = None
    pass

class MockLoader:
    def __init__(self):
        self.loaded = []
        
    def load(self, path, use_cache=True, implicit_layout=None):
        self.loaded.append((path, implicit_layout))
        
        # Return a mock class with identifying info
        class Page(MockPage):
            __file_path__ = str(path)
            # Simulate layout directive effect if implicit layout provided
            pass
            
        return Page

    def invalidate_cache(self, path=None):
        pass

class TestFileRouting(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.test_dir)
        
        self.app = PyHTML(str(self.tmp_path))
        self.app.loader = MockLoader()
        self.app.router = Router()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_scan_simple_structure(self):
        """Test standard file structure scanning."""
        # Create pages
        (self.tmp_path / "index.pyhtml").touch()
        (self.tmp_path / "about.pyhtml").touch()
        
        self.app._scan_directory(self.tmp_path)
        
        # Check routes
        routes = {r.pattern: r for r in self.app.router.routes}
        # Check regex pattern for root since / is often compiled to regex
        root_patterns = [r.regex.pattern for r in self.app.router.routes if r.pattern == '/']
        self.assertTrue(any("^/$" in p for p in root_patterns) or "/" in routes)
        self.assertIn("/about", routes)
        
    def test_scan_nested_structure(self):
        """Test nested directories and params."""
        (self.tmp_path / "index.pyhtml").touch()
        
        users = self.tmp_path / "users"
        users.mkdir()
        (users / "index.pyhtml").touch()
        (users / "[id].pyhtml").touch()
        
        posts = self.tmp_path / "posts"
        posts.mkdir()
        (posts / "[slug]").mkdir()
        (posts / "[slug]" / "index.pyhtml").touch()
        
        self.app._scan_directory(self.tmp_path)
        
        routes = {r.pattern: r for r in self.app.router.routes}
        
        self.assertIn("/", routes)
        self.assertIn("/users", routes) # users/index.pyhtml -> /users/
        
        # [id].pyhtml -> /users/{id}
        self.assertIn("/users/{id}", routes)
        
        # posts/[slug]/index.pyhtml -> /posts/{slug}/
        # Normalized by router might be different
        self.assertIn("/posts/{slug}", routes)

    def test_scan_layouts(self):
        """Test layout discovery and injection."""
        layout = self.tmp_path / "layout.pyhtml"
        layout.touch()
        
        (self.tmp_path / "index.pyhtml").touch()
        
        sub = self.tmp_path / "sub"
        sub.mkdir()
        (sub / "page.pyhtml").touch()
        
        # Sub layout
        sub_layout = sub / "layout.pyhtml"
        sub_layout.touch()
        
        self.app._scan_directory(self.tmp_path)
        
        # Check loading calls
        loaded = self.app.loader.loaded
        
        # 1. Root layout should be loaded first (implicit_layout=None)
        # Loader called with (path, implicit_layout)
        
        # Normalize paths for comparison
        # On macOS /var is link to /private/var. resolve() resolves it. 
        # But we need to be consistent.
        def norm(p):
            return str(p.resolve())
            
        loaded_normalized = [(norm(p), l) for p, l in loaded]
        
        # Root layout loading
        self.assertIn((norm(layout), None), loaded_normalized)
        
        # Index should have root layout
        self.assertIn(( norm(self.tmp_path / "index.pyhtml"), norm(layout) ), loaded_normalized)
        
        # Sub layout should be loaded with root layout as implicit!
        self.assertIn(( norm(sub_layout), norm(layout) ), loaded_normalized)
        
        # Sub page should have sub layout
        self.assertIn(( norm(sub / "page.pyhtml"), norm(sub_layout) ), loaded_normalized)

if __name__ == '__main__':
    unittest.main()
