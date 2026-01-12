import ast
import sys
import os

# Add src to path
sys.path.append(os.path.abspath("pyhtml/src"))

from pyhtml.compiler.parser import PyHTMLParser
from pyhtml.compiler.codegen.generator import CodeGenerator

def debug_directives():
    with open("demo-app/src/pages/directives.pyhtml", "r") as f:
        content = f.read()

    parser = PyHTMLParser()
    parsed = parser.parse(content)
    
    codegen = CodeGenerator()
    module = codegen.generate(parsed)
    
    print(ast.unparse(module))

if __name__ == "__main__":
    try:
        debug_directives()
    except Exception as e:
        print(f"FAILURE: {e}")
        import traceback
        traceback.print_exc()
