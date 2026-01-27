from pyhtml.runtime.app import PyHTML
from starlette.testclient import TestClient


def test_source_endpoint_requires_dev_mode_and_debug(tmp_path):
    """/_pyhtml/source only works when BOTH debug=True AND _is_dev_mode=True."""
    # Case 1: debug=True, _is_dev_mode=False (e.g. pyhtml run with debug=True)
    app = PyHTML(debug=True, pages_dir=str(tmp_path))
    # _is_dev_mode defaults to False
    client = TestClient(app)
    response = client.get("/_pyhtml/source?path=/etc/passwd")
    assert response.status_code == 404

    # Case 2: debug=False, _is_dev_mode=True (should not happen practically if
    # logic aligns, but technically possible)
    app = PyHTML(debug=False, pages_dir=str(tmp_path))
    app._is_dev_mode = True
    client = TestClient(app)
    response = client.get("/_pyhtml/source?path=/etc/passwd")
    assert response.status_code == 404

    # Case 3: Both True
    app = PyHTML(debug=True, pages_dir=str(tmp_path))
    app._is_dev_mode = True
    client = TestClient(app)

    # Create a dummy file
    test_file = tmp_path / "test.py"
    test_file.write_text("# content")

    response = client.get(f"/_pyhtml/source?path={test_file}")
    assert response.status_code == 200
    assert response.text == "# content"


def test_file_endpoint_requires_dev_mode_and_debug(tmp_path):
    """/_pyhtml/file/{encoded} gating."""
    import base64

    test_file = tmp_path / "test.py"
    test_file.write_text("# content")

    encoded_path = base64.urlsafe_b64encode(str(test_file).encode()).decode()

    # Case 1: production mode (debug=False, default)
    app = PyHTML(debug=False, pages_dir=str(tmp_path))
    client = TestClient(app)
    response = client.get(f"/_pyhtml/file/{encoded_path}")
    assert response.status_code == 404

    # Case 2: Dev mode enabled
    app = PyHTML(debug=True, pages_dir=str(tmp_path))
    app._is_dev_mode = True
    client = TestClient(app)
    response = client.get(f"/_pyhtml/file/{encoded_path}")
    assert response.status_code == 200
    assert response.text == "# content"


def test_devtools_json_requires_dev_mode(tmp_path):
    """DevTools JSON endpoint gating."""
    app = PyHTML(debug=True, pages_dir=str(tmp_path))
    # _is_dev_mode defaults to False
    client = TestClient(app)
    response = client.get("/.well-known/appspecific/com.chrome.devtools.json")
    assert response.status_code == 404

    app._is_dev_mode = True
    client = TestClient(app)
    response = client.get("/.well-known/appspecific/com.chrome.devtools.json")
    assert response.status_code == 200
    assert "workspace" in response.json()
