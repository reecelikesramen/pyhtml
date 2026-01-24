import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from pyhtml.runtime.app import PyHTML
from starlette.requests import Request


class TestAppRuntime(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.pages_dir = Path(self.test_dir)
        # Mock Starlette to avoid actual server setup
        with (
            patch("starlette.applications.Starlette"),
            patch("pyhtml.runtime.app.PageLoader"),
            patch("pyhtml.runtime.app.HTTPTransportHandler"),
            patch("pyhtml.runtime.app.WebSocketHandler"),
            patch("pyhtml.runtime.webtransport_handler.WebTransportHandler"),
        ):
            self.app = PyHTML(self.pages_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_handle_capabilities(self):
        request = MagicMock(spec=Request)
        response = await self.app._handle_capabilities(request)
        import json

        data = json.loads(response.body)
        self.assertIn("transports", data)
        self.assertEqual(data["version"], "0.0.1")

    def test_scan_directory_routing(self):
        # Create a nested structure
        (self.pages_dir / "index.pyhtml").touch()
        users = self.pages_dir / "users"
        users.mkdir()
        (users / "[id].pyhtml").touch()

        # Mock loader to return dummy classes
        self.app.loader.load = MagicMock(return_value=type("Page", (object,), {}))

        self.app.router = MagicMock()
        self.app._scan_directory(self.pages_dir)

        # Verify routes were added
        # index -> /
        # users/[id].pyhtml -> /users/{id}
        self.app.router.add_route.assert_any_call("/", unittest.mock.ANY)
        self.app.router.add_route.assert_any_call("/users/{id}", unittest.mock.ANY)

    @patch("pyhtml.runtime.app.upload_manager")
    async def test_handle_upload_invalid_token(self, mock_upload):
        request = MagicMock(spec=Request)
        request.headers = {"X-Upload-Token": "invalid"}
        response = await self.app._handle_upload(request)
        self.assertEqual(response.status_code, 403)

    @patch("pyhtml.runtime.app.upload_manager")
    async def test_handle_upload_success(self, mock_upload):
        self.app.upload_tokens.add("valid-token")
        mock_upload.save.return_value = "upload-123"

        request = AsyncMock(spec=Request)
        request.headers = {"X-Upload-Token": "valid-token"}

        # Mock form data
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        # request.form must be an async method returning the dict
        request.form = AsyncMock(return_value={"file": mock_file})

        response = await self.app._handle_upload(request)
        self.assertEqual(response.status_code, 200)
        import json

        data = json.loads(response.body)
        self.assertEqual(data["file"], "upload-123")

    def test_register_error_page(self):
        self.app.router = MagicMock()
        file_path = self.pages_dir / "broken.pyhtml"
        file_path.write_text("!path '/broken'\nINVALID PYTHON")

        self.app._register_error_page(file_path, Exception("Parse error"))

        # Should register the custom route if found via regex
        self.app.router.add_route.assert_any_call("/broken", unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
