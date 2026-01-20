from pyhtml.config import PyHTMLConfig
from pathlib import Path

config = PyHTMLConfig(
    pages_dir=Path("src/pages"),
    enable_pjax=True
)
