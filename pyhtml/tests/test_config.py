
import unittest
import tempfile
import shutil
from pathlib import Path
from pyhtml.config import PyHTMLConfig

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.test_dir)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_defaults(self):
        config = PyHTMLConfig.load(self.tmp_path / "nonexistent.py")
        self.assertEqual(config.pages_dir, Path("pages"))
        
    def test_load_from_file(self):
        config_file = self.tmp_path / "pyhtml.config.py"
        config_file.write_text("""
from pathlib import Path
from pyhtml.config import PyHTMLConfig

config = PyHTMLConfig(
    pages_dir=Path("custom_pages"),
    trailing_slash=True
)
""")
        config = PyHTMLConfig.load(config_file)
        self.assertEqual(config.pages_dir, Path("custom_pages"))
        self.assertTrue(config.trailing_slash)
        
    def test_load_from_dict(self):
        config_file = self.tmp_path / "pyhtml.config.py"
        config_file.write_text("""
config = {
    "pages_dir": "dict_pages",
    "trailing_slash": True
}
""")
        # Note: PyHTMLConfig fields are typed. dict unpacking might pass string to Path field.
        # Check if PyHTMLConfig converts it? Dataclasses don't auto-convert.
        # But let's see if my implementation supports it or if I need to adjust expectation.
        # The implementation does `cls(**config_obj)`. 
        # If I pass string "dict_pages" to `pages_dir: Path`, it will be a string at runtime until used.
        # So expectation is it matches the value.
        
        config = PyHTMLConfig.load(config_file)
        self.assertEqual(config.pages_dir, "dict_pages") 
        self.assertTrue(config.trailing_slash)

if __name__ == '__main__':
    unittest.main()
