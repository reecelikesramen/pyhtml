import ast
import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pyhtml.compiler.ast_nodes import BindAttribute, EventAttribute, ParsedPyHTML, TemplateNode
from pyhtml.compiler.codegen.generator import CodeGenerator


class TestAsyncFeatures(unittest.TestCase):
    def setUp(self):
        self.generator = CodeGenerator()

    def compile_and_get_handlers(self, template_node, python_code=""):
        parsed = ParsedPyHTML(
            template=[template_node],
            python_code=python_code,
            python_ast=ast.parse(python_code) if python_code else None,
            file_path="test_async.pyhtml",
        )

        module_ast = self.generator.generate(parsed)
        ast.fix_missing_locations(module_ast)

        handlers = {}
        for node in module_ast.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and item.name.startswith("_handler_"):
                        handlers[item.name] = item
        return handlers, parsed

    def test_implicit_async_await(self):
        # Python code with async method
        py_code = """
async def my_async_task(self):
    pass
"""

        # <button @click="my_async_task()">
        click_attr = EventAttribute(
            line=1,
            column=1,
            name="@click",
            value="my_async_task()",
            event_type="click",
            handler_name="my_async_task()",
        )

        button = TemplateNode(line=1, column=1, tag="button", special_attributes=[click_attr])

        handlers, parsed = self.compile_and_get_handlers(button, py_code)

        # Verify wrapper created
        self.assertEqual(len(handlers), 1)
        handler = list(handlers.values())[0]

        # Verify body contains await
        source = ast.unparse(handler)
        self.assertIn("await self.my_async_task()", source)
        print("\nTest Implicit Async Await Source:\n", source)

    def test_busy_binding(self):
        # <button @click="do_work" $bind:busy="is_busy">
        click_attr = EventAttribute(
            line=1,
            column=1,
            name="@click",
            value="do_work",
            event_type="click",
            handler_name="do_work",
        )
        bind_attr = BindAttribute(
            line=1,
            column=1,
            name="$bind:busy",
            value="is_busy",
            variable="is_busy",
            binding_type="busy",
        )

        button = TemplateNode(
            line=1, column=1, tag="button", special_attributes=[click_attr, bind_attr]
        )

        # Regular sync method is fine too, but let's assume it exists
        py_code = "def do_work(self): pass"

        handlers, parsed = self.compile_and_get_handlers(button, py_code)

        self.assertEqual(len(handlers), 1)
        handler = list(handlers.values())[0]
        source = ast.unparse(handler)

        # Check for busy logic
        self.assertIn("self.is_busy = True", source)
        self.assertIn("_on_update", source)
        self.assertIn("try:", source)
        self.assertIn("self.do_work()", source)
        self.assertIn("finally:", source)
        self.assertIn("self.is_busy = False", source)
        print("\nTest Busy Binding Source:\n", source)

    def test_busy_binding_with_async_call(self):
        # <button @click="my_async()" $bind:busy="loading">
        py_code = "async def my_async(self): pass"

        click_attr = EventAttribute(
            line=1,
            column=1,
            name="@click",
            value="my_async()",
            event_type="click",
            handler_name="my_async()",
        )
        bind_attr = BindAttribute(
            line=1,
            column=1,
            name="$bind:busy",
            value="loading",
            variable="loading",
            binding_type="busy",
        )

        button = TemplateNode(
            line=1, column=1, tag="button", special_attributes=[click_attr, bind_attr]
        )

        handlers, parsed = self.compile_and_get_handlers(button, py_code)
        handler = list(handlers.values())[0]
        source = ast.unparse(handler)

        self.assertIn("await self.my_async()", source)
        self.assertIn("self.loading = True", source)
        print("\nTest Busy + Async Source:\n", source)


if __name__ == "__main__":
    unittest.main()
