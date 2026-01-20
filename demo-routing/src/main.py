from pathlib import Path
from pyhtml import PyHTML

# Get the pages directory
pages_dir = Path(__file__).parent / "pages"

# Create application instance
app = PyHTML(
    pages_dir=str(pages_dir),
    enable_pjax=True
)
