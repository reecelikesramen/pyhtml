import sys
from pathlib import Path
import ast
import hashlib

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "pywire" / "src"))

from pywire.compiler.parser import PyWireParser
from pywire.compiler.codegen.generator import CodeGenerator

def inspect_file(path_str):
    print(f"\n--- Inspecting {path_str} ---")
    path = Path(path_str).resolve()
    with open(path, 'r') as f:
        content = f.read()
    
    parser = PyWireParser()
    gen = CodeGenerator()
    
    parsed = parser.parse(content)
    parsed.file_path = str(path)
    
    # Manually trigger resolution logic used in generator if needed, 
    # but generator.generate does it.
    
    module_ast = gen.generate(parsed)
    code = ast.unparse(module_ast)
    
    # Print relevant parts
    print(f"File Path: {parsed.file_path}")
    md5 = hashlib.md5(str(parsed.file_path).encode()).hexdigest()
    print(f"Expected MD5: {md5}")
    
    for line in code.splitlines():
        if "layout_id=" in line or "register_slot" in line or "register_head_slot" in line or "LAYOUT_ID =" in line:
            print(f"LOC: {line.strip()}")

if __name__ == "__main__":
    base_dir = Path(__file__).parent.resolve()
    inspect_file(base_dir / "repro_layout/layout.pywire")
    inspect_file(base_dir / "repro_layout/page.pywire")
