import ast
import unittest

from pyhtml.compiler.ast_nodes import (
    EventAttribute,
    FieldValidationRules,
    FormValidationSchema,
    ParsedPyHTML,
    TemplateNode,
)
from pyhtml.compiler.codegen.generator import CodeGenerator


class TestGeneratorExhaustive(unittest.TestCase):
    def setUp(self):
        self.generator = CodeGenerator()

    def test_process_handlers_busy_binding(self):
        # Trigger a wrapper by using a busy binding
        from pyhtml.compiler.ast_nodes import BindAttribute

        node = TemplateNode(tag="input", line=1, column=0)
        node.special_attributes = [
            EventAttribute(
                name="@input",
                value="update",
                event_type="input",
                handler_name="update",
                line=1,
                column=0,
            ),
            BindAttribute(
                name="$bind", value="busy", variable="is_忙", binding_type="busy", line=1, column=0
            ),
        ]
        parsed = ParsedPyHTML(template=[node])

        handlers = self.generator._process_handlers(parsed, set(), set())
        self.assertEqual(len(handlers), 1)

    def test_generate_form_validation_complex(self):
        # Form with validation and model
        schema = FormValidationSchema(
            fields={"email": FieldValidationRules(name="email", required=True)},
            model_name="MyModel",
        )
        node = TemplateNode(tag="form", line=1, column=0)
        node.special_attributes = [
            EventAttribute(
                name="@submit",
                value="save",
                event_type="submit",
                handler_name="save",
                validation_schema=schema,
                line=1,
                column=0,
            )
        ]
        parsed = ParsedPyHTML(template=[node])

        methods = self.generator._generate_form_validation_methods(parsed, set())
        # Check that we have a wrapper method
        wrapper = next(
            m
            for m in methods
            if isinstance(m, ast.AsyncFunctionDef) and m.name.startswith("_form_submit_")
        )
        self.assertIsNotNone(wrapper)
        # Verify it has some body content
        self.assertTrue(len(wrapper.body) > 0)

    def test_transform_user_code_globals(self):
        code = "x = 10\ndef f(): pass"
        tree = ast.parse(code)
        # _transform_user_code handles assignments and functions
        transformed = self.generator._transform_user_code(tree, set())
        self.assertEqual(len(transformed), 2)


if __name__ == "__main__":
    unittest.main()
