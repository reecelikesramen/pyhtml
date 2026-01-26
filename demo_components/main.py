from pathlib import Path
from pyhtml import PyHTML

base_dir = Path(__file__).parent
app = PyHTML(debug=True, pages_dir=base_dir / "pages")