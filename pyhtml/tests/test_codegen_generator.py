import unittest
import ast
from pyhtml.compiler.codegen.generator import CodeGenerator
from pyhtml.compiler.ast_nodes import (
    ParsedPyHTML, TemplateNode, EventAttribute, BindAttribute, 
    FormValidationSchema, FieldValidationRules
)

class TestCodeGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = CodeGenerator()

    def test_extract_user_imports(self):
        code = "import os\nfrom math import sqrt"
        tree = ast.parse(code)
        imports = self.generator._extract_user_imports(tree)
        self.assertEqual(len(imports), 2)
        self.assertIsInstance(imports[0], ast.Import)
        self.assertIsInstance(imports[1], ast.ImportFrom)

    def test_extract_user_classes(self):
        code = "class MyModel:\n    pass\n\ndef my_func():\n    pass"
        tree = ast.parse(code)
        classes = self.generator._extract_user_classes(tree)
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].name, "MyModel")

    def test_collect_global_names(self):
        code = "x = 10\ndef func(): pass\nasync def afunc(): pass"
        tree = ast.parse(code)
        methods, variables, async_methods = self.generator._collect_global_names(tree)
        self.assertIn("func", methods)
        self.assertIn("afunc", methods)
        self.assertIn("afunc", async_methods)
        self.assertIn("x", variables)
        self.assertIn("request", variables) # Default variable

    def test_generate_basic_module(self):
        parsed = ParsedPyHTML(
            template=[TemplateNode(tag="div", children=[], attributes={}, line=1, column=0)],
            python_code="name = 'World'",
            python_ast=ast.parse("name = 'World'"),
            file_path="test.pyhtml"
        )
        module = self.generator.generate(parsed)
        self.assertIsInstance(module, ast.Module)
        
        # Check for class definition
        class_defs = [n for n in module.body if isinstance(n, ast.ClassDef)]
        self.assertEqual(len(class_defs), 1)
        self.assertEqual(class_defs[0].name, "TestPage")

    def test_transform_inline_code_argument_lifting(self):
        # Test that unbound variables in arguments are lifted to parameters
        code = "update_user(user_id, 'new_name')"
        # user_id is unbound
        body, args = self.generator._transform_inline_code(code, known_methods={"update_user"})
        
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0], "user_id")
        
        # Verify the call was transformed to use arg0
        call = body[0].value
        self.assertIsInstance(call.args[0], ast.Name)
        self.assertEqual(call.args[0].id, "arg0")

    def test_process_handlers_busy_binding(self):
        # Test @click with $bind="busy"
        node = TemplateNode(tag="button", line=1, column=0)
        node.special_attributes = [
            EventAttribute(name="@click", value="do_work", event_type="click", handler_name="do_work", line=1, column=0),
            BindAttribute(name="$bind", value="is_loading", variable="is_loading", binding_type="busy", line=1, column=0)
        ]
        parsed = ParsedPyHTML(template=[node])
        
        handlers = self.generator._process_handlers(parsed, known_methods={"do_work"}, async_methods=set())
        self.assertEqual(len(handlers), 1)
        
        # Check for wrapping logic (set busy, try, finally unset busy)
        body = handlers[0].body
        self.assertIsInstance(body[0], ast.Assign) # set busy = True
        self.assertIsInstance(body[1], ast.If)     # check _on_update
        self.assertIsInstance(body[2], ast.Try)    # try block
        self.assertIsInstance(body[2].finalbody[0], ast.Assign) # set busy = False

    def test_generate_form_validation(self):
        schema = FormValidationSchema(fields={
            "email": FieldValidationRules(name="email", required=True, input_type="email")
        })
        node = TemplateNode(tag="form", line=1, column=0)
        node.special_attributes = [
            EventAttribute(name="@submit", value="save", event_type="submit", 
                           handler_name="save", validation_schema=schema, line=1, column=0)
        ]
        parsed = ParsedPyHTML(template=[node])
        
        methods = self.generator._generate_form_validation_methods(parsed, set())
        # Should have schema assignment and wrapper method
        self.assertEqual(len(methods), 2)
        self.assertIsInstance(methods[0], ast.Assign)
        self.assertIsInstance(methods[1], ast.AsyncFunctionDef)
        self.assertTrue(methods[1].name.startswith("_form_submit_"))

    def test_extract_import_names(self):
        code = "import os as my_os\nfrom math import sqrt as my_sqrt"
        tree = ast.parse(code)
        names = self.generator._extract_import_names(tree)
        self.assertIn("my_os", names)
        self.assertIn("my_sqrt", names)
        self.assertIn("json", names) 

if __name__ == "__main__":
    unittest.main()
