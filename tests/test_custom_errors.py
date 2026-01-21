import pytest
from starlette.testclient import TestClient
from pyhtml.runtime.app import PyHTML
from pathlib import Path

# Custom error pages tests

def test_default_404_no_pages_dir(tmp_path):
    """Verify default 404 when no pages directory exists."""
    app = PyHTML(pages_dir=str(tmp_path / "nonexistent"))
    client = TestClient(app)
    
    response = client.get("/not-found")
    assert response.status_code == 404
    assert "Not Found" in response.text

def test_custom_404(tmp_path):
    """Verify custom 404 page is rendered."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "404.pyhtml").write_text("<h1>Custom 404</h1>")
    
    app = PyHTML(pages_dir=str(pages_dir))
    client = TestClient(app)
    
    response = client.get("/some-missing-path")
    assert response.status_code == 404
    assert "Custom 404" in response.text

@pytest.mark.asyncio
async def test_custom_500(tmp_path):
    """Verify custom 500 page is rendered on exception."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "500.pyhtml").write_text("<h1>Custom 500</h1>")
    (pages_dir / "index.pyhtml").write_text("{ 1 / 0 }")
    
    # We need to disable the DevErrorMiddleware to see the custom 500 page
    # In PyHTML, DevErrorMiddleware is added if debug=True.
    # By default PyHTML has debug=maybe? 
    # Actually PyHTML.__init__ has debug parameter.
    
    app = PyHTML(pages_dir=str(pages_dir), debug=False)
    client = TestClient(app, raise_server_exceptions=False)
    
    # Trigger 500
    response = client.get("/")
    assert response.status_code == 500
    assert "Custom 500" in response.text
