
import unittest
import tempfile
import shutil
from pathlib import Path
from pyhtml.runtime.app import PyHTML

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.test_dir)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_default_config(self):
        # Should default to looking for 'pages' or 'src/pages' relative to cwd
        # But we can override it
        app = PyHTML(pages_dir=str(self.tmp_path), debug=True)
        self.assertEqual(app.pages_dir, self.tmp_path)
        self.assertTrue(app.debug)
        self.assertTrue(app.path_based_routing) # Default is True from user snippet

    def test_explicit_config(self):
        app = PyHTML(
            pages_dir=str(self.tmp_path / "custom"),
            path_based_routing=False,
            enable_pjax=False,
            enable_webtransport=True
        )
        self.assertEqual(app.pages_dir, self.tmp_path / "custom")
        self.assertFalse(app.path_based_routing)
        self.assertFalse(app.enable_pjax)
        self.assertTrue(app.enable_webtransport)

    def test_auto_discovery(self):
        # We can't easily test auto-discovery of CWD without mocking Path.cwd
        # causing side effects.
        # But we can test that passing None triggers the logic.
        from unittest.mock import patch
        
        with patch('pathlib.Path.cwd', return_value=self.tmp_path):
            (self.tmp_path / "src" / "pages").mkdir(parents=True)
            app = PyHTML(pages_dir=None)
            self.assertEqual(app.pages_dir, self.tmp_path / "src" / "pages")

    def test_auto_discovery_root(self):
        # Test finding 'pages' in root
        from unittest.mock import patch
        with patch('pathlib.Path.cwd', return_value=self.tmp_path):
            (self.tmp_path / "pages").mkdir()
            app = PyHTML(pages_dir=None)
            self.assertEqual(app.pages_dir, self.tmp_path / "pages")

if __name__ == '__main__':
    unittest.main()
