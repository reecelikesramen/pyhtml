import unittest
import ast
from pyhtml.compiler.codegen.template import TemplateCodegen
from pyhtml.compiler.ast_nodes import (
    TemplateNode, ForAttribute, IfAttribute, BindAttribute, 
    EventAttribute, ReactiveAttribute, ShowAttribute
)

class TestCodegenTemplateExhaustive(unittest.TestCase):
    def setUp(self):
        self.codegen = TemplateCodegen()

    def normalize_ast(self, node):
        """Ensure all nodes have lineno/col_offset for unparse."""
        if isinstance(node, list):
            for n in node: self.normalize_ast(n)
            return node
            
        for child in ast.walk(node):
            if not hasattr(child, 'lineno'):
                child.lineno = 1
                child.end_lineno = 1
                child.col_offset = 0
                child.end_col_offset = 0
        return node

    def assertCodeIn(self, snippet, statements):
        """Helper to check if snippet exists in unparsed statements."""
        self.normalize_ast(statements)
        full_code = "\n".join(ast.unparse(s) for s in statements)
        self.assertIn(snippet, full_code)

    def test_add_node_for_loop(self):
        # <template $for="item in items"><span>{item}</span></template>
        for_attr = ForAttribute(name="$for", value="item in items", is_template_tag=True, loop_vars="item", iterable="items", line=1, column=0)
        span = TemplateNode(tag="span", attributes={}, line=1, column=0)
        node = TemplateNode(tag="template", special_attributes=[for_attr], children=[span], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        
        self.assertCodeIn("async for item in self.items:", lines)
        # Check that child node was added with increased indent
        self.assertCodeIn("parts.append('<span')", lines)

    def test_add_node_if_condition(self):
        # <div $if="show_me">Content</div>
        if_attr = IfAttribute(name="$if", value="show_me", condition="show_me", line=1, column=0)
        node = TemplateNode(tag="div", special_attributes=[if_attr], children=[], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        self.assertCodeIn("if self.show_me:", lines)

    def test_add_node_bind_checkbox(self):
        # <input type="checkbox" $bind="is_active">
        bind = BindAttribute(name="$bind", value="is_active", variable="is_active", binding_type="property", line=1, column=0)
        node = TemplateNode(tag="input", attributes={"type": "checkbox"}, special_attributes=[bind], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        # Check for checked binding logic
        self.assertCodeIn("if self.is_active:", lines)
        self.assertCodeIn("attrs['checked'] = ''", lines)

    def test_add_node_bind_select(self):
        # <select $bind="selected_val"><option value="1">One</option></select>
        bind = BindAttribute(name="$bind", value="selected_val", variable="selected_val", binding_type="property", line=1, column=0)
        option = TemplateNode(tag="option", attributes={"value": "1"}, children=[], line=1, column=0)
        node = TemplateNode(tag="select", attributes={}, special_attributes=[bind], children=[option], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        # Check that option has selected logic based on bound_var
        self.assertCodeIn("if 'value' in attrs and str(attrs['value']) == str(self.selected_val):", lines)
        self.assertCodeIn("attrs['selected'] = ''", lines)

    def test_add_node_reactive_boolean(self):
        # <button :disabled="is_disabled">Click</button>
        reactive = ReactiveAttribute(name="disabled", value="is_disabled", expr="is_disabled", line=1, column=0)
        node = TemplateNode(tag="button", special_attributes=[reactive], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        # Should handle HTML boolean attribute (presence/absence)
        self.assertCodeIn("if _r_val is True:", lines)
        self.assertCodeIn("attrs['disabled'] = ''", lines)

    def test_add_node_show_attribute(self):
        # <div $show="is_visible">...</div>
        show = ShowAttribute(name="$show", value="is_visible", condition="is_visible", line=1, column=0)
        node = TemplateNode(tag="div", special_attributes=[show], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        self.assertCodeIn("if not self.is_visible:", lines)
        self.assertCodeIn("attrs['style'] = attrs.get('style', '') + '; display: none'", lines)

    def test_add_node_event_with_args(self):
        # <button @click="delete_user(user.id)">Delete</button>
        event = EventAttribute(name="@click", value="delete_user(user.id)", event_type="click", 
                               handler_name="delete_user", args=["user.id"], line=1, column=0)
        node = TemplateNode(tag="button", special_attributes=[event], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines, local_vars={"user"})
        # Should encode arguments to data-arg-0
        self.assertCodeIn("attrs['data-arg-0'] = json.dumps(user.id)", lines)

if __name__ == "__main__":
    unittest.main()
