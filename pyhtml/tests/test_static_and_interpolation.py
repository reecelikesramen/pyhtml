
import pytest
from pathlib import Path
from starlette.testclient import TestClient
from pyhtml.runtime.app import PyHTML
from pyhtml.compiler.parser import PyHTMLParser

def test_interpolation_ignore_in_script_and_style(tmp_path):
    """Verify that {} in script and style tags are treated as literal text."""
    
    # Create a page with script and style tags containing curly braces
    page_content = """
    <div>
        <script>
            const x = {a: 1, b: 2};
            function test() { return {c: 3}; }
        </script>
        <style>
            body { color: red; }
            .class { font-size: 12px; }
        </style>
        <p>Real interpolation: {1 + 1}</p>
    </div>
    ---
    ---
    """
    
    (tmp_path / "page.pyhtml").write_text(page_content, encoding='utf-8')
    
    # Parse the file directly to check AST nodes
    parser = PyHTMLParser()
    parsed = parser.parse(page_content, str(tmp_path / "page.pyhtml"))
    
    # Check script content
    div_node = next(n for n in parsed.template if n.tag == 'div')
    # Find script node among children
    script_node = next(n for n in div_node.children if n.tag == 'script')
    assert script_node.tag == 'script'
    # The children of script should be text nodes. 
    # If interpolation was attempted, we might see InterpolationNode or split string nodes.
    # We want to see a single string node (or multiple string nodes) but NO InterpolationNode.
    
    def has_interpolation(nodes):
        from pyhtml.compiler.ast_nodes import InterpolationNode
        for node in nodes:
            if isinstance(node, InterpolationNode):
                return True
            # Also check if text content looks suspicious (if parser failed to parse interpolation but kept braces, that's good)
            # But the parser currently parses {a: 1} as interpolation if logical.
            # {a: 1} is valid python set/dict syntax? Set: {1}. Dict: {'a':1}. 
            # JS object {a: 1} is valid Python set if 'a' is a var? No, {a:1} is invalid syntax in Python unless dict.
            # {a: 1} is INVALID python dict (needs quotes keys). 
            # So parser._is_valid_python might return False, and it treats as literal.
            # BUT {a} IS valid python set.
            pass
        return False
        
    # Let's inspect the children of script
    print(f"Script children: {script_node.children}")
    
    # Also verify runtime rendering
    app = PyHTML(str(tmp_path))
    client = TestClient(app)
    
    response = client.get("/page")
    assert response.status_code == 200
    content = response.text
    
    assert "const x = {a: 1, b: 2};" in content
    assert "body { color: red; }" in content
    assert "<p>Real interpolation: 2</p>" in content

def test_static_asset_serving(tmp_path):
    """Verify static asset serving."""
    
    # Create pages dir
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "index.pyhtml").write_text("<div>Home</div>", encoding='utf-8')
    
    # Create static dir
    static_dir = tmp_path / "static_assets"
    static_dir.mkdir()
    (static_dir / "style.css").write_text("body { background: blue; }", encoding='utf-8')
    
    # Initialize app with static_dir
    # Note: static_dir is resolved relative to CWD in the plan.
    # To test this integration properly we might need to chdir or mock CWD, 
    # OR pass absolute path if implementation allows it?
    # The plan said "Resolve it relative to CWD". 
    # But usually Path(d).resolve() handles absolute paths fine. 
    # If I pass absolute path, it should work.
    
    app = PyHTML(pages_dir=str(pages_dir), static_dir=str(static_dir))
    client = TestClient(app)
    
    # Request static file
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert response.text == "body { background: blue; }"
    
    # Verify default is disabled
    app_default = PyHTML(pages_dir=str(pages_dir)) # No static_dir
    client_default = TestClient(app_default)
    response_default = client_default.get("/static/style.css")
    assert response_default.status_code == 404

