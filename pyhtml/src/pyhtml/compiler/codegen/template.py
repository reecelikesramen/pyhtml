"""Template rendering code generation."""
import ast
import re
from dataclasses import dataclass, replace
from typing import List, Set, Tuple

from pyhtml.compiler.ast_nodes import (
    InterpolationNode, TemplateNode, SpecialAttribute, EventAttribute,
    IfAttribute, ShowAttribute, ForAttribute, BindAttribute, KeyAttribute
)
from pyhtml.compiler.interpolation.jinja import JinjaInterpolationParser


@dataclass
class BindingDef:
    """Definition of a generated binding."""
    handler_name: str
    variable_name: str
    event_type: str  # 'input' or 'change'


class TemplateCodegen:
    """Generates Python code for rendering template."""

    # HTML void elements that don't have closing tags
    VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                     'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        self.interpolation_parser = JinjaInterpolationParser()
        self.generated_bindings: List[BindingDef] = []
        self._binding_counter = 0

    def generate_render_code(self, template_nodes: List[TemplateNode]) -> str:
        """Generate complete render code."""
        # Reset state
        self.generated_bindings = []
        self._binding_counter = 0
        
        code_lines = ['def _render_template(self):', '    parts = []']
        
        def transform_expr(expr: str, local_vars: Set[str]) -> str:
            """Transform expression to use self. for non-local variables."""
            # Simple identifiers
            if expr.replace('_', '').isalnum() and not expr[0].isdigit():
                if expr in local_vars:
                    return expr
                # builtins check?
                if expr in {'True', 'False', 'None'}:
                    return expr
                return f'self.{expr}'

            # Complex expressions using AST
            try:
                expr_ast = ast.parse(expr, mode='eval')
                
                class AddSelfTransformer(ast.NodeTransformer):
                    def visit_Name(self, node):
                        builtins = {'True', 'False', 'None', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'enumerate', 'len', 'range', 'zip'}
                        if node.id not in builtins and node.id not in local_vars:
                            return ast.Attribute(
                                value=ast.Name(id='self', ctx=ast.Load()),
                                attr=node.id,
                                ctx=node.ctx
                            )
                        return node
                
                transformer = AddSelfTransformer()
                new_ast = transformer.visit(expr_ast)
                ast.fix_missing_locations(new_ast)
                return ast.unparse(new_ast.body).strip()
            except:
                # Fallback regex
                def repl(m):
                    word = m.group(1)
                    if word in local_vars: return word
                    keywords = {'if', 'else', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None', 'for', 'while'}
                    if word in keywords: return word
                    return f'self.{word}'
                
                return re.sub(r'\b([a-zA-Z_]\w*)\b(?!\s*[(\[])', repl, expr)

        def add_node(node: TemplateNode, indent: int = 1, local_vars: Set[str] = None, bound_var: str = None):
            if local_vars is None:
                local_vars = set()
            
            indent_str = '    ' * indent

            # 1. Handle $for (highest precedence / wrapper)
            for_attr = next((a for a in node.special_attributes if isinstance(a, ForAttribute)), None)
            if for_attr:
                # Parse loop vars
                loop_vars_str = for_attr.loop_vars
                new_locals = local_vars.copy()
                for var in loop_vars_str.split(','):
                    new_locals.add(var.strip())
                
                # Transform iterable
                iterable = transform_expr(for_attr.iterable, local_vars)
                
                # Emit loop
                code_lines.append(f'{indent_str}for {loop_vars_str} in {iterable}:')
                
                # Recurse on same node but without $for
                new_attrs = [a for a in node.special_attributes if a is not for_attr]
                # If it's a <template $for>, and we want to unwrap it, we should check tag
                if node.tag == 'template':
                    # Unwrap children of template
                    for child in node.children:
                        add_node(child, indent + 1, new_locals, bound_var)
                else:
                    # Generic element, just process it
                    new_node = replace(node, special_attributes=new_attrs)
                    add_node(new_node, indent + 1, new_locals, bound_var)
                return

            # 2. Handle $if
            if_attr = next((a for a in node.special_attributes if isinstance(a, IfAttribute)), None)
            if if_attr:
                cond = transform_expr(if_attr.condition, local_vars)
                code_lines.append(f'{indent_str}if {cond}:')
                
                # Recurse without $if
                new_attrs = [a for a in node.special_attributes if a is not if_attr]
                new_node = replace(node, special_attributes=new_attrs)
                add_node(new_node, indent + 1, local_vars, bound_var)
                return
            
            # 3. Render Node
            if node.tag is None:
                # Text node
                if node.text_content:
                    parts = self.interpolation_parser.parse(node.text_content, node.line, node.column)
                    if len(parts) == 1 and isinstance(parts[0], str):
                        code_lines.append(f'{indent_str}parts.append({repr(node.text_content)})')
                    else:
                        # Compile interpolation with local vars support
                        expr_parts = []
                        for part in parts:
                            if isinstance(part, str):
                                expr_parts.append(repr(part))
                            else:
                                # Interpolation object
                                transformed = transform_expr(part.expression, local_vars)
                                expr_parts.append(f'str({transformed})')
                        
                        full_expr = ' + '.join(expr_parts)
                        code_lines.append(f'{indent_str}parts.append({full_expr})')
                else:
                     # Interpolation node in special_attributes
                    for attr in node.special_attributes:
                        if isinstance(attr, InterpolationNode):
                            expr = transform_expr(attr.expression, local_vars)
                            code_lines.append(f'{indent_str}parts.append(str({expr}))')
            
            else:
                # Element Node
                
                # Process $bind
                bind_attr = next((a for a in node.special_attributes if isinstance(a, BindAttribute)), None)
                bindings = {} # attr -> value_expr
                new_bound_var = bound_var # Propagate existing unless overridden
                
                if bind_attr:
                    var_name = bind_attr.variable
                    
                    self._binding_counter += 1
                    handler_name = f'_handle_bind_{self._binding_counter}'
                    
                    # Determine event type and attribute
                    tag = node.tag.lower()
                    input_type = node.attributes.get('type', 'text')
                    
                    if tag == 'input' and input_type in ('checkbox', 'radio'):
                         # Checkbox
                         event_type = 'change'
                         target_var = transform_expr(var_name, local_vars)
                         bindings['checked'] = target_var # Boolean? 
                    elif tag == 'select':
                        event_type = 'input'
                        target_var = transform_expr(var_name, local_vars)
                        bindings['value'] = f'str({target_var})'
                        new_bound_var = target_var # Set bound var for children options
                    else:
                        # Text, textarea
                        event_type = 'input'
                        target_var = transform_expr(var_name, local_vars)
                        bindings['value'] = f'str({target_var})'
                    
                    # Add binding handler definition
                    self.generated_bindings.append(BindingDef(
                        handler_name=handler_name,
                        variable_name=var_name, 
                        event_type=event_type
                    ))
                    
                    # Add event handler attribute
                    bindings[f'data-on-{event_type}'] = repr(handler_name)
                    
                # Process $show
                show_attr = next((a for a in node.special_attributes if isinstance(a, ShowAttribute)), None)
                
                # Process $key
                key_attr = next((a for a in node.special_attributes if isinstance(a, KeyAttribute)), None)
                if key_attr:
                    bindings['id'] = f'str({transform_expr(key_attr.expr, local_vars)})'


                # --- Generate Attribute Construction Code ---
                code_lines.append(f'{indent_str}attrs = {{}}')
                
                # Static/Regular attributes
                for k, v in node.attributes.items():
                    # Check for interpolation in attribute value
                    if '{' in v and '}' in v:
                        parts = self.interpolation_parser.parse(v, node.line, node.column)
                        expr_parts = []
                        for part in parts:
                            if isinstance(part, str):
                                expr_parts.append(repr(part))
                            else:
                                transformed = transform_expr(part.expression, local_vars)
                                expr_parts.append(f'str({transformed})')
                        full_expr = ' + '.join(expr_parts)
                        code_lines.append(f'{indent_str}attrs[{repr(k)}] = {full_expr}')
                    else:
                        code_lines.append(f'{indent_str}attrs[{repr(k)}] = {repr(v)}')

                # Bindings
                for k, v in bindings.items():
                    if k == 'checked':
                        # Special handling for boolean
                        code_lines.append(f'{indent_str}if {v}:')
                        code_lines.append(f'{indent_str}    attrs["checked"] = ""')
                    else:
                         code_lines.append(f'{indent_str}attrs[{repr(k)}] = {v}')

                # Event attributes
                for attr in node.special_attributes:
                    if isinstance(attr, EventAttribute):
                        code_lines.append(f'{indent_str}attrs["data-on-{attr.event_type}"] = {repr(attr.handler_name)}')
                        
                        # Arguments for handler
                        for i, arg_expr in enumerate(attr.args):
                             val = transform_expr(arg_expr, local_vars)
                             code_lines.append(f'{indent_str}attrs["data-arg-{i}"] = json.dumps({val})')

                # Handle $show
                if show_attr:
                    cond = transform_expr(show_attr.condition, local_vars)
                    code_lines.append(f'{indent_str}if not {cond}:')
                    code_lines.append(f'{indent_str}    attrs["style"] = attrs.get("style", "") + "; display: none"')
                    
                # Handle <option> 'selected' if inside bound select
                if node.tag.lower() == 'option' and bound_var:
                    # Get 'value' attribute
                    # We need to know the value. It might be in attrs or bindings.
                    # It's usually in attrs['value'] (static or interpolated).
                    # We can try to extract it from 'attrs' dict in runtime?
                    # The code above generated `attrs[...] = ...`.
                    # We can append a check *after* attrs construction.
                    code_lines.append(f'{indent_str}if "value" in attrs and str(attrs["value"]) == str({bound_var}):')
                    code_lines.append(f'{indent_str}    attrs["selected"] = ""')

                # Render open tag
                code_lines.append(f'{indent_str}header_parts = []')
                code_lines.append(f'{indent_str}for k, v in attrs.items():')
                code_lines.append(f'{indent_str}    val = str(v).replace(\'"\', \'&quot;\')')
                code_lines.append(f'{indent_str}    header_parts.append(f\' {{k}}="{{val}}"\')')
                
                code_lines.append(f'{indent_str}parts.append(f"<{node.tag}{{\'\'.join(header_parts)}}>")')

                # Children
                for child in node.children:
                    add_node(child, indent, local_vars, new_bound_var) # Pass new_bound_var

                # Close tag
                if node.tag.lower() not in self.VOID_ELEMENTS:
                    code_lines.append(f'{indent_str}parts.append("</{node.tag}>")')

        for node in template_nodes:
            add_node(node)

        code_lines.append('    return "".join(parts)')
        return '\n'.join(code_lines)
