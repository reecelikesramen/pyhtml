from starlette.testclient import TestClient
from pyhtml.runtime.app import PyHTML
from pathlib import Path
import pytest

def test_prod_load_error_shows_500(tmp_path):
    """Verify that in production (debug=False), load errors show generic 500, not CompileErrorPage."""
    
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    
    # Create custom 500 page
    (pages_dir / "500.pyhtml").write_text("<h1>Custom 500 Error</h1>")
    
    # Create page with load-time error
    bad_page = pages_dir / "bad.pyhtml"
    bad_page.write_text("""
!path "/bad"
---
raise Exception("Secret Info Leak")
""")
    
    # Initialize in PROD mode
    app = PyHTML(
        pages_dir=str(pages_dir),
        debug=False
    )
    # Ensure not dev mode
    app._is_dev_mode = False
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # Request the bad page
    response = client.get("/bad")
    
    # Expectation: 
    # 1. 500 status code
    # 2. Content should be Custom 500 page
    # 3. Content should NOT contain "Secret Info Leak" or "CompileErrorPage"
    
    print(f"DEBUG Response Status: {response.status_code}")
    print(f"DEBUG Response Content: {response.text}")
    
    assert response.status_code == 500
    assert "Custom 500 Error" in response.text
    assert "Secret Info Leak" not in response.text
    assert "PyHTML Syntax Error" not in response.text

if __name__ == "__main__":
    import sys
    try:
        pytest.main([__file__, "-v"])
    except SystemExit as e:
        sys.exit(e.code)
