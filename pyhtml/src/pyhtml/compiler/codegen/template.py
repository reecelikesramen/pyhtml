"""Template rendering code generation."""
from typing import List

from pyhtml.compiler.ast_nodes import InterpolationNode, SpecialAttribute, TemplateNode
from pyhtml.compiler.interpolation.jinja import JinjaInterpolationParser


class TemplateCodegen:
    """Generates Python code for rendering template."""

    def __init__(self):
        self.interpolation_parser = JinjaInterpolationParser()

    def generate_render_method(self, template_nodes: List[TemplateNode]) -> str:
        """Generate _render_template method body."""
        lines = ['def _render_template(self):', '    parts = []']
        
        for node in template_nodes:
            self._generate_node(node, lines, indent=1)

        lines.append('    return "".join(parts)')
        return '\n'.join('    ' * indent + line if line else '' for indent, line in enumerate(lines.split('\n')))

    def _generate_node(self, node: TemplateNode, lines: List[str], indent: int = 0):
        """Generate code for a template node."""
        indent_str = '    ' * indent

        if node.tag is None:
            # Text node
            if node.text_content:
                # Regular text
                lines.append(f'{indent_str}parts.append({repr(node.text_content)})')
            else:
                # Interpolation node
                for attr in node.special_attributes:
                    if isinstance(attr, InterpolationNode):
                        lines.append(f'{indent_str}parts.append(str(self.{attr.expression}))')
        else:
            # Element node
            tag = node.tag
            attrs_parts = []

            # Regular attributes
            for name, value in node.attributes.items():
                attrs_parts.append(f'{name}={repr(value)}')

            # Special attributes (for HTML generation)
            for attr in node.special_attributes:
                if hasattr(attr, 'event_type'):
                    # Event attribute - generate data attribute
                    attrs_parts.append(f'data-on-{attr.event_type}={repr(attr.handler_name)}')

            attrs_str = ', '.join(attrs_parts) if attrs_parts else ''
            open_tag = f'<{tag}' + (f' {attrs_str}' if attrs_str else '') + '>'
            lines.append(f'{indent_str}parts.append({repr(open_tag)})')

            # Children
            for child in node.children:
                self._generate_node(child, lines, indent + 1)

            # Closing tag
            lines.append(f'{indent_str}parts.append({repr(f"</{tag}>")})')

    def generate_render_code(self, template_nodes: List[TemplateNode]) -> str:
        """Generate complete render code."""
        code_lines = ['def _render_template(self):', '    parts = []']
        
        def add_node(node: TemplateNode, indent: int = 1):
            indent_str = '    ' * indent

            if node.tag is None:
                # Text node
                if node.text_content:
                    # Regular text - check for interpolations
                    # Parse text content for interpolations
                    parts = self.interpolation_parser.parse(node.text_content, node.line, node.column)
                    if len(parts) == 1 and isinstance(parts[0], str):
                        # Pure text, no interpolation
                        code_lines.append(f'{indent_str}parts.append({repr(node.text_content)})')
                    else:
                        # Has interpolations - use f-string
                        compiled = self.interpolation_parser.compile(node.text_content)
                        code_lines.append(f'{indent_str}parts.append({compiled})')
                else:
                    # Interpolation node stored in special_attributes
                    for attr in node.special_attributes:
                        if isinstance(attr, InterpolationNode):
                            import ast as ast_module
                            expr = attr.expression
                            
                            # For simple identifiers, add self.
                            if expr.replace('_', '').isalnum() and not expr[0].isdigit():
                                code_lines.append(f'{indent_str}parts.append(str(self.{expr}))')
                            else:
                                # Complex expression - use AST to add self. to Name nodes
                                try:
                                    expr_ast = ast_module.parse(expr, mode='eval')
                                    
                                    class AddSelfTransformer(ast_module.NodeTransformer):
                                        def visit_Name(self, node):
                                            # Don't transform builtins and keywords
                                            builtins = {'True', 'False', 'None', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple'}
                                            if node.id not in builtins:
                                                # Transform to Attribute access: name -> self.name
                                                return ast_module.Attribute(
                                                    value=ast_module.Name(id='self', ctx=ast_module.Load()),
                                                    attr=node.id,
                                                    ctx=node.ctx
                                                )
                                            return node
                                    
                                    transformer = AddSelfTransformer()
                                    new_ast = transformer.visit(expr_ast)
                                    ast_module.fix_missing_locations(new_ast)
                                    
                                    # Convert back to code (Python 3.9+)
                                    modified_expr = ast_module.unparse(new_ast.body).strip()
                                    code_lines.append(f'{indent_str}parts.append(str({modified_expr}))')
                                except:
                                    # Fallback: use regex approach
                                    import re
                                    keywords = {'if', 'else', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None', 'for', 'while'}
                                    modified_expr = re.sub(
                                        r'\b([a-zA-Z_]\w*)\b(?!\s*[(\[])',
                                        lambda m: f'self.{m.group(1)}' if m.group(1) not in keywords else m.group(1),
                                        expr
                                    )
                                    code_lines.append(f'{indent_str}parts.append(str({modified_expr}))')
            else:
                # Element node
                attrs = []
                
                # Build HTML attributes string
                attr_parts = []
                for name, value in node.attributes.items():
                    # Escape quotes in value
                    escaped_value = str(value).replace('"', '&quot;')
                    attr_parts.append(f'{name}="{escaped_value}"')

                # Special attributes
                for attr in node.special_attributes:
                    if hasattr(attr, 'event_type'):
                        attr_parts.append(f'data-on-{attr.event_type}="{attr.handler_name}"')

                # Build HTML tag string
                if attr_parts:
                    attrs_str = ' '.join(attr_parts)
                    open_tag = f'<{node.tag} {attrs_str}>'
                else:
                    open_tag = f'<{node.tag}>'
                code_lines.append(f'{indent_str}parts.append({repr(open_tag)})')

                # Children
                for child in node.children:
                    add_node(child, indent)

                code_lines.append(f'{indent_str}parts.append({repr(f"</{node.tag}>")})')

        for node in template_nodes:
            add_node(node)

        code_lines.append('    return "".join(parts)')
        return '\n'.join(code_lines)
