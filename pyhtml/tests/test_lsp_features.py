
import pytest
from pyhtml_lsp.server import PyHTMLDocument

def test_extract_routes_dict():
    text = """!path { 'main': '/main', 'detail': '/detail/:id' }
---
def setup():
    pass
"""
    doc = PyHTMLDocument('file:///test.pyhtml', text)
    routes = doc.routes
    assert len(routes) == 2
    assert routes['main'] == '/main'
    assert routes['detail'] == '/detail/:id'

def test_extract_routes_string():
    text = """!path '/simple'
---
"""
    doc = PyHTMLDocument('file:///test.pyhtml', text)
    routes = doc.routes
    assert len(routes) == 1
    assert routes['main'] == '/simple'

def test_extract_routes_empty():
    text = """
<div />
"""
    doc = PyHTMLDocument('file:///test.pyhtml', text)
    assert len(doc.routes) == 0

if __name__ == "__main__":
    try:
        test_extract_routes_dict()
        test_extract_routes_string()
        test_extract_routes_empty()
        print("LSP tests passed!")
    except AssertionError as e:
        print(f"LSP test failed: {e}")
        raise
