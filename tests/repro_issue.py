from starlette.testclient import TestClient
from pyhtml.runtime.app import PyHTML
from pathlib import Path
import pytest
import shutil

def test_syntax_error_not_rendering(tmp_path):
    """Reproduce situation: debug=False, path_based_routing=False, SyntaxError in page."""
    
    # Create pages dir
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    
    # Create valid layout
    (pages_dir / "layout.pyhtml").write_text("""
    <html><body><slot></slot></body></html>
    """)
    
    # Create page with SyntaxError and explicit path
    # Using /// - which caused the user's issue
    bad_page = pages_dir / "dx_demo.pyhtml"
    bad_page.write_text("""
!path "/dx_demo"
<div id="demo"></div>
---
log_count = /// -
""")

    # Initialize app like the user did
    app = PyHTML(
        pages_dir=str(pages_dir),
        path_based_routing=False,
        debug=False
    )
    # Note: in dev mode, _is_dev_mode would be True. Let's set it.
    app._is_dev_mode = True
    
    client = TestClient(app)
    
    # Verify console output would show failure (implicit in app init)
    
    # Request the page
    response = client.get("/dx_demo")
    
    print(f"Status Code: {response.status_code}")
    print(f"Content Type: {response.headers.get('content-type')}")
    print(f"Content preview: {response.text[:200]}")
    
    # Expectation: 200 OK with Error Page content
    assert response.status_code == 200
    assert "PyHTML Syntax Error" in response.text
    assert "dx_demo.pyhtml" in response.text

if __name__ == "__main__":
    import sys
    try:
        pytest.main([__file__, "-v"])
    except SystemExit as e:
        sys.exit(e.code)
