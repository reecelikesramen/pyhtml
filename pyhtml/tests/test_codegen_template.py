import ast
import unittest

from pyhtml.compiler.ast_nodes import InterpolationNode, TemplateNode
from pyhtml.compiler.codegen.template import TemplateCodegen


class TestCodegenTemplate(unittest.TestCase):
    def setUp(self):
        self.codegen = TemplateCodegen()

    def normalize_ast(self, node):
        """Ensure all nodes have lineno/col_offset for unparse."""
        if isinstance(node, list):
            for n in node:
                self.normalize_ast(n)
            return node

        for child in ast.walk(node):
            if not hasattr(child, "lineno"):
                child.lineno = 1
                child.end_lineno = 1
                child.col_offset = 0
                child.end_col_offset = 0
        return node

    def assertASTEqual(self, ast_node, expected_code):
        """Helper to compare AST node equal to expected code string."""
        self.normalize_ast(ast_node)

        # Normalize by parsing the expected code
        if isinstance(ast_node, ast.AST):
            generated_code = ast.unparse(ast_node).strip()
            self.assertEqual(generated_code, expected_code)
        elif isinstance(ast_node, list):
            # For list of statements
            generated_code = "\n".join(ast.unparse(n) for n in ast_node).strip()
            self.assertEqual(generated_code, expected_code)
        else:
            self.fail(f"Unexpected AST type: {type(ast_node)}")

    def test_transform_expr_basic(self):
        # name should become self.name
        expr = "name == 'Admin' and age > 18"
        transformed = self.codegen._transform_expr(expr, local_vars=set())
        self.assertASTEqual(transformed, "self.name == 'Admin' and self.age > 18")

    def test_transform_expr_with_locals(self):
        # item is local, should NOT get self. prefix
        expr = "item.name == 'Test'"
        transformed = self.codegen._transform_expr(expr, local_vars={"item"})
        self.assertASTEqual(transformed, "item.name == 'Test'")

    def test_transform_reactive_expr_auto_call(self):
        # Parameterless method should be auto-called
        expr = "my_method"
        transformed = self.codegen._transform_reactive_expr(
            expr, local_vars=set(), known_methods={"my_method"}
        )
        self.assertASTEqual(transformed, "self.my_method()")

    def test_transform_reactive_expr_async(self):
        # Async method should be awaited
        expr = "get_data()"
        transformed = self.codegen._transform_reactive_expr(
            expr, local_vars=set(), async_methods={"get_data"}
        )
        self.assertASTEqual(transformed, "await self.get_data()")

    def test_generate_render_method(self):
        # Interpolation must be wrapped in a TemplateNode with tag=None
        interp_node = InterpolationNode(line=1, column=0, expression="msg")
        text_wrapper = TemplateNode(tag=None, special_attributes=[interp_node], line=1, column=0)
        node = TemplateNode(tag="div", children=[text_wrapper], line=1, column=0)

        func_def, aux = self.codegen.generate_render_method([node])

        self.normalize_ast(func_def)
        code = ast.unparse(func_def)
        self.assertIn("async def _render_template(self):", code)
        self.assertIn("parts = []", code)
        self.assertIn("import json", code)
        self.assertIn("parts.append('<div')", code)  # unparse uses single quotes often?
        self.assertIn("parts.append(str(self.msg))", code)
        self.assertIn("parts.append('</div>')", code)
        self.assertIn("return ''.join(parts)", code)

    def test_generate_slot_methods(self):
        # Node with slot filler: <slot name="header">...</slot>
        node = TemplateNode(
            tag="slot",
            attributes={"name": "header"},
            children=[TemplateNode(tag=None, text_content="Header content", line=1, column=0)],
            line=1,
            column=0,
        )

        slots, aux = self.codegen.generate_slot_methods([node], file_id="test")
        self.assertIn("header", slots)

        # slots["header"] is an AsyncFunctionDef
        func_def = slots["header"]
        self.normalize_ast(func_def)
        code = ast.unparse(func_def)

        self.assertIn("async def _render_slot_fill_header_", code)
        self.assertIn("parts.append('Header content')", code)


if __name__ == "__main__":
    unittest.main()
