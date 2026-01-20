import unittest
from pyhtml.compiler.parser import PyHTMLParser
from pyhtml.compiler.ast_nodes import EventAttribute

class TestParserAdvanced(unittest.TestCase):
    def setUp(self):
        self.parser = PyHTMLParser()

    def test_extract_all_validation_rules(self):
        content = """
<form @submit="save">
    <input name="t1" type="text" required minlength="2" maxlength="10" pattern="[a-z]+">
    <input name="n1" type="number" min="0" max="100" step="5">
    <input name="f1" type="file" accept="image/*,.pdf" max-size="5mb">
    <textarea name="area" required title="Please fill"></textarea>
    <select name="sel">
        <option value="1">One</option>
    </select>
</form>
"""
        parsed = self.parser.parse(content)
        form = parsed.template[0]
        submit = next(a for a in form.special_attributes if isinstance(a, EventAttribute))
        fields = submit.validation_schema.fields
        
        # Text
        self.assertTrue(fields["t1"].required)
        self.assertEqual(fields["t1"].minlength, 2)
        self.assertEqual(fields["t1"].maxlength, 10)
        self.assertEqual(fields["t1"].pattern, "[a-z]+")
        
        # Number
        self.assertEqual(fields["n1"].min_value, "0")
        self.assertEqual(fields["n1"].max_value, "100")
        self.assertEqual(fields["n1"].step, "5")
        
        # File
        self.assertEqual(fields["f1"].allowed_types, ["image/*", ".pdf"])
        self.assertEqual(fields["f1"].max_size, 5 * 1024 * 1024)
        
        # Textarea
        self.assertEqual(fields["area"].input_type, "textarea")
        self.assertEqual(fields["area"].title, "Please fill")
        
        # Select
        self.assertEqual(fields["sel"].input_type, "select")

    def test_reactive_validation_rules(self):
        content = """
<form @submit="save">
    <input name="email" :required="is_required" :min="min_age" :max="max_age">
</form>
"""
        parsed = self.parser.parse(content)
        form = parsed.template[0]
        submit = next(a for a in form.special_attributes if isinstance(a, EventAttribute))
        field = submit.validation_schema.fields["email"]
        
        self.assertEqual(field.required_expr, "is_required")
        self.assertEqual(field.min_expr, "min_age")
        self.assertEqual(field.max_expr, "max_age")

if __name__ == "__main__":
    unittest.main()
