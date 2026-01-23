import unittest
import ast
from pyhtml.compiler.ast_nodes import ParsedPyHTML, TemplateNode, EventAttribute
from pyhtml.compiler.codegen.generator import CodeGenerator
from pyhtml.compiler.parser import PyHTMLParser

class TestInteractivityCodegenComplex(unittest.TestCase):
    def setUp(self):
        self.generator = CodeGenerator()
        self.parser = PyHTMLParser()

    def test_inline_argument_lifting(self):
        """Test that @click="delete_item(item.id, 'confirm')" lifts arguments."""
        template = '<button @click="delete_item(item.id, \'confirmed\')">Delete</button>'
        # Mock python code with the handler method
        python_code = 'async def delete_item(id, status): pass'
        content = f'{template}\n---\n{python_code}'
        parsed = self.parser.parse(content)
        
        # Generate code
        module_ast = self.generator.generate(parsed)
        code = ast.unparse(module_ast)
        
        # Verify handler method generation
        # Since it's an async method in the python block, it should be awaited
        self.assertIn('async def _handler_0(self, arg0):', code)
        self.assertIn('await self.delete_item(arg0, \'confirmed\')', code)
        
        # Verify render template call
        # It should pass the arguments to the generator
        self.assertIn('data-arg-0', code)
        self.assertNotIn('data-arg-1', code) # 'confirmed' is a literal, not lifted

    def test_multiple_handlers_complex(self):
        """Verify behavior with multiple handlers having arguments and modifiers."""
        template = '<button @click.stop="foo(id1)" @click.prevent="bar(id2)">Click</button>'
        parsed = self.parser.parse(template)
        
        module_ast = self.generator.generate(parsed)
        code = ast.unparse(module_ast)
        
        # Verify JSON contains args placeholders (since they are lifted)
        # AST codegen produces direct list assignment: _h['args'] = [self.id1]
        self.assertIn("_h['args'] = [self.id1]", code)
        self.assertIn("_h['args'] = [self.id2]", code)
        # Verify modifiers are collected (order is unstable because of set())
        modifiers_line = [l for l in code.split('\n') if "attrs['data-modifiers-click'] =" in l][0]
        self.assertIn('stop', modifiers_line)
        self.assertIn('prevent', modifiers_line)

    def test_busy_binding(self):
        """Test that $bind:busy wraps the handler in try/finally with busy state changes."""
        template = '<button @click="do_work" $bind:busy="is_busy">Work</button>'
        python_code = 'async def do_work(): pass'
        content = f'{template}\n---\n{python_code}'
        parsed = self.parser.parse(content)
        
        module_ast = self.generator.generate(parsed)
        code = ast.unparse(module_ast)
        
        # Verify busy state logic
        self.assertIn('self.is_busy = True', code)
        self.assertIn('self.is_busy = False', code)
        self.assertIn('try:', code)
        self.assertIn('finally:', code)
        self.assertIn('await self.do_work()', code)

    def test_form_validation_wrapper(self):
        """Test that @submit on a form with validation schema generates a wrapper."""
        # This requires more setup (mocking a validation schema in the AST)
        # For now, let's verify if the generator handles EventAttribute with validation_schema
        from pyhtml.compiler.ast_nodes import FormValidationSchema, FieldValidationRules
        
        template = '<form @submit="save"><input name="user"></form>'
        parsed = self.parser.parse(template)
        
        # Manually inject a validation schema for the test
        for attr in parsed.template[0].special_attributes:
            if isinstance(attr, EventAttribute) and attr.event_type == 'submit':
                attr.validation_schema = FormValidationSchema(
                    fields={
                        'user': FieldValidationRules(name='user', required=True, minlength=3)
                    }
                )
        
        module_ast = self.generator.generate(parsed)
        code = ast.unparse(module_ast)
        
        # Verify wrapper generation
        self.assertIn('async def _form_submit_0(self, **kwargs):', code)
        self.assertIn('form_validator.validate_form', code)
        self.assertIn('self._form_schema_0.fields', code)
        self.assertIn('await self.save(cleaned_data)', code)

if __name__ == "__main__":
    unittest.main()
