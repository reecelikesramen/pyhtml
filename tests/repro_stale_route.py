from starlette.testclient import TestClient
from pyhtml.runtime.app import PyHTML
from pathlib import Path
import pytest
import time

def test_reload_replaces_stale_route(tmp_path):
    """Verify that reloading a page with error removes the old valid route."""
    
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    
    # helper to write file
    demo_file = pages_dir / "demo.pyhtml"
    
    # 1. Create valid page
    demo_file.write_text("""
!path "/demo"
<h1>Valid Page</h1>
""")
    
    app = PyHTML(pages_dir=str(pages_dir), debug=True)
    app._is_dev_mode = True
    client = TestClient(app)
    
    # Check initial valid response
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert "Valid Page" in resp.text
    
    # 2. Update with Syntax Error
    demo_file.write_text("""
!path "/demo"
<h1>Broken Page</h1>
---
x = ///
""")
    
    # 3. Simulate reload (normally done by file watcher)
    # The file watcher calls app.reload_page(path)
    try:
        app.reload_page(demo_file)
    except Exception:
        # reload_page re-raises the exception, which is expected
        pass
        
    # 4. Check response again
    # If the bug is present, the router will still match the OLD valid page route
    # If fixed, it should match the NEW error page route
    resp = client.get("/demo")
    
    print(f"Response: {resp.text[:100]}")
    
    # Should be the CompileErrorPage (which says "PyHTML Syntax Error")
    # NOT the "Valid Page"
    assert "Valid Page" not in resp.text
    assert "PyHTML Syntax Error" in resp.text

if __name__ == "__main__":
    import sys
    try:
        pytest.main([__file__, "-v"])
    except SystemExit as e:
        sys.exit(e.code)
