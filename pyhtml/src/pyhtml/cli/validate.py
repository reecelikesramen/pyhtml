"""Validation for .pyhtml files."""
from pathlib import Path
from typing import List

from pyhtml.compiler.parser import PyHTMLParser


def validate_project(pages_dir: Path) -> List[str]:
    """Validate all .pyhtml files in project."""
    errors = []
    parser = PyHTMLParser()

    if not pages_dir.exists():
        return [f"Pages directory not found: {pages_dir}"]

    for pyhtml_file in pages_dir.rglob('*.pyhtml'):
        try:
            parsed = parser.parse_file(pyhtml_file)
            # Basic validation
            if not parsed.template and not parsed.directives:
                errors.append(f"{pyhtml_file}: No template or directives found")
        except Exception as e:
            errors.append(f"{pyhtml_file}: {str(e)}")

    return errors
