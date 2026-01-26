from pyhtml.compiler.parser import PyHTMLParser
from pyhtml.compiler.codegen.generator import CodeGenerator
import ast

parser = PyHTMLParser()
gen = CodeGenerator()

content = '<div :id="dynamic_id">Test</div>'
parsed = parser.parse(content)
parsed.file_path = "test.pyhtml"
module_ast = gen.generate(parsed)

code = ast.unparse(module_ast)
print(code)



print(f"File path: '{parsed.file_path}'")
if 'data-ph-' in code:
    print("Found data-ph- in generated code!")
    # Find the line
    for line in code.splitlines():
        if 'data-ph-' in line:
            print(f"Line: {line.strip()}")
else:
    print("No data-ph- found.")
