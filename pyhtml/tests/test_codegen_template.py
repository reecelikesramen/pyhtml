import unittest
from pyhtml.compiler.codegen.template import TemplateCodegen
from pyhtml.compiler.ast_nodes import TemplateNode, IfAttribute, InterpolationNode

class TestCodegenTemplate(unittest.TestCase):
    def setUp(self):
        self.codegen = TemplateCodegen()

    def test_transform_expr_basic(self):
        # name should become self.name
        expr = "name == 'Admin' and age > 18"
        transformed = self.codegen._transform_expr(expr, local_vars=set())
        self.assertEqual(transformed, "self.name == 'Admin' and self.age > 18")

    def test_transform_expr_with_locals(self):
        # item is local, should NOT get self. prefix
        expr = "item.name == 'Test'"
        transformed = self.codegen._transform_expr(expr, local_vars={"item"})
        self.assertEqual(transformed, "item.name == 'Test'")

    def test_transform_reactive_expr_auto_call(self):
        # Parameterless method should be auto-called
        expr = "my_method"
        transformed = self.codegen._transform_reactive_expr(
            expr, local_vars=set(), known_methods={"my_method"}
        )
        self.assertEqual(transformed, "self.my_method()")

    def test_transform_reactive_expr_async(self):
        # Async method should be awaited
        expr = "get_data()"
        transformed = self.codegen._transform_reactive_expr(
            expr, local_vars=set(), async_methods={"get_data"}
        )
        self.assertEqual(transformed, "await self.get_data()")

    def test_generate_render_method(self):
        # Interpolation must be wrapped in a TemplateNode with tag=None
        interp_node = InterpolationNode(line=1, column=0, expression="msg")
        text_wrapper = TemplateNode(tag=None, special_attributes=[interp_node], line=1, column=0)
        node = TemplateNode(tag="div", children=[text_wrapper], line=1, column=0)
        
        render_code, aux_funcs = self.codegen.generate_render_method([node])
        self.assertIn("def _render_template(self):", render_code)
        # Element tags are generated with dynamic attributes
        self.assertIn("parts.append(f\"<div", render_code)
        self.assertIn("parts.append(str(self.msg))", render_code)
        self.assertIn("parts.append(\"</div>\")", render_code)

    def test_generate_slot_methods(self):
        # Node with slot filler: <slot name="header">...</slot>
        node = TemplateNode(tag="slot", attributes={"name": "header"}, children=[
            TemplateNode(tag=None, text_content="Header content", line=1, column=0)
        ], line=1, column=0)
        
        slots, aux = self.codegen.generate_slot_methods([node], file_id="test")
        self.assertIn("header", slots)
        # It uses MD5 hash of "test", so we check for prefix
        self.assertIn("def _render_slot_fill_header_", slots["header"])
        self.assertIn("Header content", slots["header"])

if __name__ == "__main__":
    unittest.main()
