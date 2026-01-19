from pathlib import Path
from pyhtml.compiler.parser import PyHTMLParser
from pyhtml.compiler.codegen.generator import CodeGenerator
import ast

parser = PyHTMLParser()
generator = CodeGenerator()

file_path = Path("/Users/rholmdahl/projects/pyhtml/demo-app/src/pages/test_multiline.pyhtml")
parsed = parser.parse_file(file_path)
module_ast = generator.generate(parsed)

print(ast.unparse(module_ast))
