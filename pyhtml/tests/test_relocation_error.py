import base64
from pathlib import Path

import msgpack # type: ignore[import-untyped]
import pytest
from typing import Any, cast
from pyhtml.runtime.app import PyHTML
from starlette.testclient import TestClient


@pytest.fixture
def app_dev(tmp_path: Path) -> PyHTML:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "index.pyhtml").write_text(
        "!path { 'a': '/a', 'b': '/b' }\n<h1>Index</h1>\n---\n# Python"
    )

    app = PyHTML(pages_dir=str(pages_dir), debug=True)
    app._is_dev_mode = True
    return app


def test_source_relocation_endpoint(app_dev: PyHTML, tmp_path: Path) -> None:
    client = TestClient(app_dev.app)

    # Test /_pyhtml/source
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")

    response = client.get(f"/_pyhtml/source?path={test_file}")
    assert response.status_code == 200
    assert response.text == "print('hello')"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"

    # Test /_pyhtml/file (base64 encoded)
    # Using URL-safe base64 logic from app.py
    filename = str(test_file)
    encoded = base64.b64encode(filename.encode()).decode()
    encoded = encoded.replace("+", "-").replace("/", "_").rstrip("=")

    response = client.get(f"/_pyhtml/file/{encoded}")
    assert response.status_code == 200
    assert response.text == "print('hello')"


def test_source_relocation_security(app_dev: PyHTML) -> None:
    client = TestClient(app_dev.app)

    # Should 404 if debug is off
    app_dev.debug = False
    response = client.get("/_pyhtml/source?path=/etc/passwd")
    assert response.status_code == 404

    # Should 404 if not in dev mode
    app_dev.debug = True
    app_dev._is_dev_mode = False
    response = client.get("/_pyhtml/source?path=/etc/passwd")
    assert response.status_code == 404


def test_spa_relocation_failure_forces_reload(app_dev: PyHTML) -> None:
    client = TestClient(app_dev.app)

    with client.websocket_connect("/_pyhtml/ws") as websocket:
        # Trigger a relocation to a non-existent path that will cause an error
        # normally _handle_relocate catches route not found and serves 404 page,
        # but if we FORCE an exception in the router or page creation, it should trigger 'reload'.

        # We can mock the router to throw
        original_match = app_dev.router.match

        def mock_match(path: str) -> Any:
            if path == "/fail-hard":
                raise RuntimeError("Hard failure")
            return original_match(path)

        cast(Any, app_dev.router).match = mock_match

        websocket.send_bytes(msgpack.packb({"type": "relocate", "path": "/fail-hard"}))

        data_bytes = websocket.receive_bytes()
        data = msgpack.unpackb(data_bytes, raw=False)

        assert data["type"] == "reload"
