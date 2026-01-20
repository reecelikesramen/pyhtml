import unittest
import asyncio
import uuid
import msgpack
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request
from starlette.responses import Response

from pyhtml.runtime.http_transport import HTTPTransportHandler, HTTPSession
from pyhtml.runtime.page import BasePage

class MockPage(BasePage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_called = False
        self.success = False

    async def on_load(self):
        self.load_called = True

    async def test(self, **kwargs):
        """Handler for 'test' events."""
        self.success = True

    async def render(self, init=True):
        return Response("success" if self.success else "<html></html>")

class TestTransportExhaustive(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock()
        self.handler = HTTPTransportHandler(self.app)

    def test_session_expiry(self):
        session = HTTPSession(session_id="1", path="/")
        self.assertFalse(session.is_expired())
        
        session.last_poll = datetime.now() - timedelta(seconds=400)
        self.assertTrue(session.is_expired(timeout_seconds=300))

    async def _async_create_session(self, body=None, content_type='application/x-msgpack', query_params=None):
        request = AsyncMock(spec=Request)
        request.body.return_value = body or b""
        request.query_params = query_params or {}
        return await self.handler.create_session(request)

    def test_create_session_msgpack(self):
        data = {'path': '/test'}
        body = msgpack.packb(data)
        
        self.app.router.match.return_value = (MockPage, {}, "main")
        
        response = asyncio.run(self._async_create_session(body=body))
        
        self.assertEqual(response.status_code, 200)
        resp_data = msgpack.unpackb(response.body, raw=False)
        self.assertIn('sessionId', resp_data)
        
        sid = resp_data['sessionId']
        self.assertIn(sid, self.handler.sessions)
        self.assertEqual(self.handler.sessions[sid].path, '/test')
        self.assertIsInstance(self.handler.sessions[sid].page, MockPage)
        self.assertTrue(self.handler.sessions[sid].page.load_called)

    def test_create_session_json_fallback(self):
        data = {'path': '/json'}
        body = json.dumps(data).encode()
        
        self.app.router.match.return_value = (MockPage, {}, "main")
        
        response = asyncio.run(self._async_create_session(body=body))
        
        resp_data = msgpack.unpackb(response.body, raw=False)
        sid = resp_data['sessionId']
        self.assertEqual(self.handler.sessions[sid].path, '/json')

    def test_create_session_empty_body(self):
        self.app.router.match.return_value = (MockPage, {}, "main")
        
        response = asyncio.run(self._async_create_session(body=b""))
        
        resp_data = msgpack.unpackb(response.body, raw=False)
        sid = resp_data['sessionId']
        self.assertEqual(self.handler.sessions[sid].path, '/')

    def test_poll_not_found(self):
        request = MagicMock(spec=Request)
        request.query_params = {'session': 'missing'}
        
        response = asyncio.run(self.handler.poll(request))
        self.assertEqual(response.status_code, 404)

    def test_poll_pending_updates(self):
        session = HTTPSession(session_id="s1", path="/")
        session.pending_updates.append({'type': 'test'})
        self.handler.sessions["s1"] = session
        
        request = MagicMock(spec=Request)
        request.query_params = {'session': 's1'}
        
        response = asyncio.run(self.handler.poll(request))
        
        self.assertEqual(response.status_code, 200)
        data = msgpack.unpackb(response.body, raw=False)
        self.assertEqual(data[0]['type'], 'test')
        self.assertEqual(len(session.pending_updates), 0)

    def test_poll_timeout(self):
        session = HTTPSession(session_id="s1", path="/")
        self.handler.sessions["s1"] = session
        
        request = MagicMock(spec=Request)
        request.query_params = {'session': 's1'}
        
        def timeout_side_effect(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError

        with patch('asyncio.wait_for', side_effect=timeout_side_effect):
            response = asyncio.run(self.handler.poll(request))
            self.assertEqual(response.status_code, 200)
            data = msgpack.unpackb(response.body, raw=False)
            self.assertEqual(data, [])

    def test_handle_event_success(self):
        session = HTTPSession(session_id="s1", path="/")
        session.page = MockPage(MagicMock(), {}, {})
        self.handler.sessions["s1"] = session
        
        request = AsyncMock(spec=Request)
        request.headers = {'X-PyHTML-Session': 's1'}
        request.body.return_value = msgpack.packb({'handler': 'test', 'data': {'x': 1}})
        
        response = asyncio.run(self.handler.handle_event(request))
        
        self.assertEqual(response.status_code, 200)
        data = msgpack.unpackb(response.body, raw=False)
        self.assertEqual(data['type'], 'update')
        self.assertIn('success', data['html'])

    def test_handle_event_recreate_page(self):
        session = HTTPSession(session_id="s1", path="/recreate")
        session.page = None
        self.handler.sessions["s1"] = session
        
        self.app.router.match.return_value = (MockPage, {}, "main")
        
        request = AsyncMock(spec=Request)
        request.headers = {'X-PyHTML-Session': 's1'}
        request.body.return_value = msgpack.packb({'handler': 'test'})
        request.query_params = {}
        
        response = asyncio.run(self.handler.handle_event(request))
        
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(session.page, MockPage)

    def test_handle_event_error(self):
        session = HTTPSession(session_id="s1", path="/")
        session.page = MockPage(MagicMock(), {}, {})
        self.handler.sessions["s1"] = session
        
        request = AsyncMock(spec=Request)
        request.headers = {'X-PyHTML-Session': 's1'}
        request.body.side_effect = Exception("Body error")
        
        response = asyncio.run(self.handler.handle_event(request))
        self.assertEqual(response.status_code, 500)
        data = msgpack.unpackb(response.body, raw=False)
        self.assertEqual(data['type'], 'error')

    def test_queue_update_and_broadcast(self):
        session = HTTPSession(session_id="s1", path="/")
        self.handler.sessions["s1"] = session
        
        self.handler.queue_update("s1", {'type': 'msg'})
        self.assertEqual(len(session.pending_updates), 1)
        self.assertTrue(session.update_event.is_set())
        
        self.handler.broadcast_reload()
        self.assertEqual(len(session.pending_updates), 2)
        self.assertEqual(session.pending_updates[-1]['type'], 'reload')

    def test_cleanup_loop(self):
        session1 = HTTPSession(session_id="s1", path="/")
        session2 = HTTPSession(session_id="s2", path="/")
        session2.last_poll = datetime.now() - timedelta(seconds=400)
        
        self.handler.sessions = {"s1": session1, "s2": session2}
        
        # Patch sleep to return immediately and stop after one iteration
        with patch('asyncio.sleep', side_effect=[None, asyncio.CancelledError]), \
             patch('builtins.print'):
            try:
                asyncio.run(self.handler._cleanup_loop())
            except asyncio.CancelledError:
                pass
        
        self.assertIn("s1", self.handler.sessions)
        self.assertNotIn("s2", self.handler.sessions)

if __name__ == "__main__":
    unittest.main()
