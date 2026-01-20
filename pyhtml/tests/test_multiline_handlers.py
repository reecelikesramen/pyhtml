"""Tests for triple-quoted multiline handler support."""
import pytest
from pyhtml.compiler.parser import PyHTMLParser


def test_triple_quote_parsing():
    """Verify triple-quoted event handlers are parsed correctly."""
    content = '''
<button @click="""
    x = 1
    print('hello')
""">Click</button>
---
'''
    parsed = PyHTMLParser().parse(content)
    
    # Should have one template node (the button)
    assert len(parsed.template) == 1
    button = parsed.template[0]
    assert button.tag == 'button'
    
    # Should have one special attribute (the @click handler)
    assert len(button.special_attributes) == 1
    handler = button.special_attributes[0]
    assert handler.event_type == 'click'
    
    # Handler value should contain the multiline content
    assert 'x = 1' in handler.handler_name
    assert "print('hello')" in handler.handler_name


def test_triple_quote_with_inner_quotes():
    """Verify inner double quotes are handled correctly."""
    content = '''
<button @click="""
    data = {"key": "value"}
    print(data["key"])
""">Click</button>
---
'''
    parsed = PyHTMLParser().parse(content)
    
    button = parsed.template[0]
    handler = button.special_attributes[0]
    
    # The handler should contain the dict literal (quotes will be &quot; internally)
    # After lxml parsing, &quot; becomes " again
    assert 'data' in handler.handler_name
    assert 'key' in handler.handler_name


def test_triple_quote_directive():
    """Verify triple-quoted directive values work."""
    content = '''
<div $for="""
    item in [
        {'name': 'Alice'},
        {'name': 'Bob'}
    ]
""">
    <p>{item['name']}</p>
</div>
---
'''
    parsed = PyHTMLParser().parse(content)
    
    div = parsed.template[0]
    # Should have a $for special attribute
    for_attr = None
    for attr in div.special_attributes:
        if hasattr(attr, 'name') and attr.name == '$for':
            for_attr = attr
            break
    
    assert for_attr is not None


def test_mixed_quote_styles():
    """Verify standard quotes still work alongside triple quotes."""
    content = '''
<button @click="simple_handler">Simple</button>
<button @click="""
    complex = True
""">Complex</button>
---
'''
    parsed = PyHTMLParser().parse(content)
    
    # Filter for button elements (ignore text/whitespace nodes)
    buttons = [n for n in parsed.template if n.tag == 'button']
    assert len(buttons) == 2
    
    # First button has simple handler
    simple = buttons[0]
    assert simple.special_attributes[0].handler_name == 'simple_handler'
    
    # Second button has complex handler
    complex_btn = buttons[1]
    assert 'complex = True' in complex_btn.special_attributes[0].handler_name


if __name__ == "__main__":
    test_triple_quote_parsing()
    test_triple_quote_with_inner_quotes()
    test_triple_quote_directive()
    test_mixed_quote_styles()
    print("All multiline handler tests passed!")
