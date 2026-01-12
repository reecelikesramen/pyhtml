
import ast
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from pyhtml.compiler.codegen.generator import CodeGenerator
from pyhtml.compiler.ast_nodes import ParsedPyHTML, TemplateNode, EventAttribute

def test_inline_handler_extraction():
    generator = CodeGenerator()
    
    # Create template with inline handler
    # <button @click="count += 1">
    click_attr = EventAttribute(
        line=1, column=1, name='@click', value='count += 1',
        event_type='click', handler_name='count += 1'
    )
    
    button_node = TemplateNode(
        line=1, column=1, tag='button',
        special_attributes=[click_attr]
    )
    
    parsed = ParsedPyHTML(
        template=[button_node],
        file_path="test_inline.pyhtml"
    )
    
    print("Compiling inline handler 'count += 1'...")
    module_ast = generator.generate(parsed)
    ast.fix_missing_locations(module_ast)
    
    # Check if a handler method was created
    found_handler = False
    for node in module_ast.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name.startswith('_handler_'):
                    print(f"Found synthetic handler: {item.name}")
                    found_handler = True
                    # Unparse body to check transformation
                    if hasattr(ast, 'unparse'):
                         print("Body source:", ast.unparse(item))
                    
    if not found_handler:
        print("FAILURE: No synthetic handler created!")
        sys.exit(1)
        
    # Check if attribute was updated
    if not click_attr.handler_name.startswith('_handler_'):
        print(f"FAILURE: Attribute handler_name was not updated correctly! Got: {click_attr.handler_name}")
        sys.exit(1)
        
    print(f"Attribute updated to: {click_attr.handler_name}")
    print("SUCCESS: Inline handler extraction verified.")

if __name__ == "__main__":
    test_inline_handler_extraction()
