# Mock jinja2
class Environment:
    def __init__(self, *args, **kwargs):
        pass
    def from_string(self, source):
        return Template(source)

class Template:
    def __init__(self, source):
        self.source = source
    def render(self, *args, **kwargs):
        return self.source # basic bypass
        
class BaseLoader:
    pass

class TemplateSyntaxError(Exception):
    pass
