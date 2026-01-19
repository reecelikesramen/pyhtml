
import ast
from pyhtml.compiler.codegen.generator import CodeGenerator
from pyhtml.compiler.parser import PyHTMLParser

def debug_file(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    
    parser = PyHTMLParser()
    parsed = parser.parse(content, file_path)
    
    generator = CodeGenerator()
    module = generator.generate(parsed)
    
    print(ast.unparse(module))

debug_file('/Users/rholmdahl/projects/pyhtml/demo-app/src/pages/chatbot/index.pyhtml')
