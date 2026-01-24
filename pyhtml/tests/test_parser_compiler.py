import unittest

from pyhtml.compiler.ast_nodes import InterpolationNode, LayoutDirective
from pyhtml.compiler.parser import PyHTMLParser


class TestParserCompiler(unittest.TestCase):
    def setUp(self):
        self.parser = PyHTMLParser()

    def test_parse_simple_html(self):
        content = "<div><span>Hello</span></div>"
        parsed = self.parser.parse(content)
        self.assertEqual(len(parsed.template), 1)
        root = parsed.template[0]
        self.assertEqual(root.tag, "div")
        self.assertEqual(len(root.children), 1)
        self.assertEqual(root.children[0].tag, "span")

    def test_parse_with_python(self):
        content = """<h1>Title</h1>\n---\nname = 'World'\ndef hello(): pass"""
        parsed = self.parser.parse(content)
        self.assertEqual(parsed.template[0].tag, "h1")
        self.assertIn("name = 'World'", parsed.python_code)
        self.assertIsNotNone(parsed.python_ast)

    def test_parse_interpolation(self):
        content = "<div>Hello {name}!</div>"
        parsed = self.parser.parse(content)
        div = parsed.template[0]
        self.assertEqual(len(div.children), 3)
        # Interpolation is wrapped in a TemplateNode with tag=None
        interp_wrapper = div.children[1]
        self.assertIsNone(interp_wrapper.tag)
        self.assertIsInstance(interp_wrapper.special_attributes[0], InterpolationNode)
        self.assertEqual(interp_wrapper.special_attributes[0].expression, "name")

    def test_parse_directives(self):
        content = "!layout 'main.pyhtml'\n<div>Content</div>"
        parsed = self.parser.parse(content)
        self.assertEqual(len(parsed.directives), 1)
        self.assertIsInstance(parsed.directives[0], LayoutDirective)
        self.assertEqual(parsed.directives[0].layout_path, "main.pyhtml")

    def test_extract_form_validation(self):
        content = """
<form @submit="save">
    <input name="email" type="email" required minlength="5">
    <input name="age" type="number" min="18">
</form>
"""
        parsed = self.parser.parse(content)
        form = parsed.template[0]
        # The parser extracts validation schema for forms with @submit
        submit_attr = next(a for a in form.special_attributes if a.name == "@submit")
        self.assertIsNotNone(submit_attr.validation_schema)
        fields = submit_attr.validation_schema.fields
        self.assertIn("email", fields)
        self.assertTrue(fields["email"].required)
        self.assertEqual(fields["email"].minlength, 5)
        self.assertEqual(fields["age"].min_value, "18")


if __name__ == "__main__":
    unittest.main()
