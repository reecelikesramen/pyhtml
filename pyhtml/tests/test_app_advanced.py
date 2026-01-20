import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pyhtml.runtime.app import PyHTML
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from pathlib import Path

class TestAppAdvanced(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pages_dir = Path("/tmp/empty_pages")
        self.pages_dir.mkdir(exist_ok=True)
        with patch('starlette.applications.Starlette'), \
             patch('pyhtml.runtime.app.PageLoader'), \
             patch('pyhtml.runtime.app.HTTPTransportHandler'), \
             patch('pyhtml.runtime.app.WebSocketHandler'), \
             patch('pyhtml.runtime.webtransport_handler.WebTransportHandler'):
            self.app = PyHTML(self.pages_dir)
            self.app.router = MagicMock()

    async def test_handle_request_post_event(self):
        # Mocking a POST request with X-PyHTML-Event header
        request = AsyncMock(spec=Request)
        request.method = "POST"
        request.headers = {"X-PyHTML-Event": "click"}
        request.url.path = "/test"
        request.json.return_value = {"handler": "save", "data": {}}
        
        page_class = MagicMock()
        self.app.router.match.return_value = (page_class, {}, "main")
        
        # Mock page instance
        page_inst = MagicMock()
        page_inst.handle_event = AsyncMock(return_value=JSONResponse({"success": True}))
        page_class.return_value = page_inst
        
        response = await self.app._handle_request(request)
        self.assertEqual(response.status_code, 200)
        page_inst.handle_event.assert_called_once_with("save", {"handler": "save", "data": {}})

    async def test_handle_request_injection(self):
        # Test injection of scripts/meta tags
        request = AsyncMock(spec=Request)
        request.method = "GET"
        request.url.path = "/test"
        request.app.state.webtransport_cert_hash = [1, 2, 3]
        
        page_class = MagicMock()
        self.app.router.match.return_value = (page_class, {}, "main")
        
        # Mock page instance with upload needs
        page_inst = MagicMock()
        page_inst.__has_uploads__ = True
        page_inst.render = AsyncMock(return_value=Response("<html><body></body></html>", media_type="text/html"))
        page_class.return_value = page_inst
        
        response = await self.app._handle_request(request)
        body = response.body.decode()
        self.assertIn("window.PYHTML_CERT_HASH", body)
        self.assertIn('name="pyhtml-upload-token"', body)

if __name__ == "__main__":
    unittest.main()
