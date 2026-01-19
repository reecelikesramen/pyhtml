import ast

try:
    print("Attempting to parse 'await foo()'")
    ast.parse("await foo()")
    print("Success parsing 'await foo()'")
except SyntaxError as e:
    print(f"Failed parsing 'await foo()': {e}")

try:
    print("Attempting to parse 'async def t(): await foo()'")
    ast.parse("async def t(): await foo()")
    print("Success parsing 'async def t(): await foo()'")
except SyntaxError as e:
    print(f"Failed parsing 'async def t(): await foo()': {e}")
