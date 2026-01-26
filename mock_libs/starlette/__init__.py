# Mock starlette package
class Request:
    def __init__(self, scope, receive=None, send=None):
        self.scope = scope
        self.app = scope.get('app')

class Response:
    def __init__(self, content, media_type=None, status_code=200):
        self.body = content.encode() if isinstance(content, str) else content
        self.media_type = media_type
