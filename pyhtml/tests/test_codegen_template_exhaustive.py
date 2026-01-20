import unittest
from pyhtml.compiler.codegen.template import TemplateCodegen
from pyhtml.compiler.ast_nodes import (
    TemplateNode, ForAttribute, IfAttribute, BindAttribute, 
    EventAttribute, ReactiveAttribute, ShowAttribute
)

class TestCodegenTemplateExhaustive(unittest.TestCase):
    def setUp(self):
        self.codegen = TemplateCodegen()

    def test_add_node_for_loop(self):
        # <template $for="item in items"><span>{item}</span></template>
        for_attr = ForAttribute(name="$for", value="item in items", is_template_tag=True, loop_vars="item", iterable="items", line=1, column=0)
        span = TemplateNode(tag="span", attributes={}, line=1, column=0)
        node = TemplateNode(tag="template", special_attributes=[for_attr], children=[span], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        
        self.assertIn("for item in self.items:", lines[0])
        # Check that child node was added with increased indent
        self.assertTrue(any("    parts.append(f\"<span" in l for l in lines))

    def test_add_node_if_condition(self):
        # <div $if="show_me">Content</div>
        if_attr = IfAttribute(name="$if", value="show_me", condition="show_me", line=1, column=0)
        node = TemplateNode(tag="div", special_attributes=[if_attr], children=[], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        self.assertIn("if self.show_me:", lines[0])

    def test_add_node_bind_checkbox(self):
        # <input type="checkbox" $bind="is_active">
        bind = BindAttribute(name="$bind", value="is_active", variable="is_active", binding_type="property", line=1, column=0)
        node = TemplateNode(tag="input", attributes={"type": "checkbox"}, special_attributes=[bind], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        # Check for checked binding logic
        self.assertTrue(any("if self.is_active:" in l for l in lines))
        self.assertTrue(any("attrs[\"checked\"] = \"\"" in l for l in lines))

    def test_add_node_bind_select(self):
        # <select $bind="selected_val"><option value="1">One</option></select>
        bind = BindAttribute(name="$bind", value="selected_val", variable="selected_val", binding_type="property", line=1, column=0)
        option = TemplateNode(tag="option", attributes={"value": "1"}, children=[], line=1, column=0)
        node = TemplateNode(tag="select", attributes={}, special_attributes=[bind], children=[option], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        # Check that option has selected logic based on bound_var
        self.assertTrue(any("if \"value\" in attrs and str(attrs[\"value\"]) == str(self.selected_val):" in l for l in lines))
        self.assertTrue(any("attrs[\"selected\"] = \"\"" in l for l in lines))

    def test_add_node_reactive_boolean(self):
        # <button :disabled="is_disabled">Click</button>
        reactive = ReactiveAttribute(name="disabled", value="is_disabled", expr="is_disabled", line=1, column=0)
        node = TemplateNode(tag="button", special_attributes=[reactive], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        # Should handle HTML boolean attribute (presence/absence)
        self.assertTrue(any("if _r_val is True:" in l for l in lines))
        self.assertTrue(any("attrs['disabled'] = \"\"" in l for l in lines))

    def test_add_node_show_attribute(self):
        # <div $show="is_visible">...</div>
        show = ShowAttribute(name="$show", value="is_visible", condition="is_visible", line=1, column=0)
        node = TemplateNode(tag="div", special_attributes=[show], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines)
        self.assertTrue(any("if not self.is_visible:" in l for l in lines))
        self.assertTrue(any("attrs[\"style\"] = attrs.get(\"style\", \"\") + \"; display: none\"" in l for l in lines))

    def test_add_node_event_with_args(self):
        # <button @click="delete_user(user.id)">Delete</button>
        event = EventAttribute(name="@click", value="delete_user(user.id)", event_type="click", 
                               handler_name="delete_user", args=["user.id"], line=1, column=0)
        node = TemplateNode(tag="button", special_attributes=[event], line=1, column=0)
        
        lines = []
        self.codegen._add_node(node, lines, local_vars={"user"})
        # Should encode arguments to data-arg-0
        self.assertTrue(any("attrs[\"data-arg-0\"] = json.dumps(user.id)" in l for l in lines))

if __name__ == "__main__":
    unittest.main()
