"""Template rendering code generation."""
import ast
import re
from dataclasses import dataclass, replace
from typing import List, Set, Tuple, Dict, Optional
from collections import defaultdict

from pyhtml.compiler.ast_nodes import (
    InterpolationNode, TemplateNode, SpecialAttribute, EventAttribute,
    IfAttribute, ShowAttribute, ForAttribute, BindAttribute, KeyAttribute, ReactiveAttribute
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
                     'link', 'meta', 'param', 'source', 'track', 'wbr', 'slot'}

    def __init__(self):
        self.interpolation_parser = JinjaInterpolationParser()
        self.generated_bindings: List[BindingDef] = []
        self._binding_counter = 0
        self._slot_default_counter = 0
        self.auxiliary_functions: List[str] = []

    def generate_render_method(self, template_nodes: List[TemplateNode], layout_id: str = None, 
                             known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None) -> Tuple[str, List[str]]:
        """
        Generate standard _render_template method.
        Returns: (main_function_body_str, list_of_auxiliary_function_strs)
        """
        self._reset_state()
        main_func = self._generate_function(template_nodes, '_render_template', is_async=True, layout_id=layout_id,
                                          known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
        return main_func, self.auxiliary_functions

    def generate_slot_methods(self, template_nodes: List[TemplateNode], file_id: str = "", known_globals: Set[str] = None) -> Tuple[Dict[str, str], List[str]]:
        """
        Generate slot filler methods for child pages.
        Returns: ({slot_name: function_code}, list_of_auxiliary_function_strs)
        file_id is used to create unique method names to prevent override in inheritance chain.
        
        Slot syntax:
        - <slot name="foo">content</slot> -> fills named slot "foo"
        - <pyhtml-head>content</pyhtml-head> -> appends to $head slot
        - Other top-level nodes -> fill default slot
        """
        self._reset_state()
        slots = defaultdict(list)
        
        # Generate a short hash from file_id to make method names unique per file
        import hashlib
        file_hash = hashlib.md5(file_id.encode()).hexdigest()[:8] if file_id else ""
        
        # 1. Bucket nodes into slots based on wrapper elements
        for node in template_nodes:
            # Check for <slot name="..."> wrapper
            if node.tag == 'slot' and node.attributes and 'name' in node.attributes:
                slot_name = node.attributes['name']
                # The slot's children are the content
                for child in node.children:
                    slots[slot_name].append(child)
            # Check for <pyhtml-head> wrapper (becomes $head slot)
            elif node.tag == 'pyhtml-head':
                for child in node.children:
                    slots['$head'].append(child)
            else:
                # Top-level nodes go to default slot
                slots['default'].append(node)
            
        # 2. Generate functions for each slot
        slot_funcs = {}
        for slot_name, nodes in slots.items():
            # Sanitize slot name for valid Python identifier
            safe_name = slot_name.replace('$', '_head_').replace('-', '_') if slot_name.startswith('$') else slot_name.replace('-', '_')
            # Include file hash to prevent method override in inheritance
            func_name = f'_render_slot_fill_{safe_name}_{file_hash}' if file_hash else f'_render_slot_fill_{safe_name}'
            slot_funcs[slot_name] = self._generate_function(nodes, func_name, is_async=True, known_globals=known_globals)
            
        return slot_funcs, self.auxiliary_functions

    def generate_head_content_method(self, template_nodes: List[TemplateNode]) -> Tuple[Optional[str], List[str]]:
        """
        Extract <head> elements from child page and generate _render_head_content.
        Returns: (function_code or None if no head, auxiliary_functions)
        """
        self._reset_state()
        
        # Find <head> elements and collect their children
        head_children = []
        for node in template_nodes:
            if node.tag == 'head':
                head_children.extend(node.children)
        
        if not head_children:
            return None, []
        
        # Generate function for head content
        func_code = self._generate_function(head_children, '_render_head_content', is_async=True)
        return func_code, self.auxiliary_functions

    def _reset_state(self):
        self.generated_bindings = []
        self._binding_counter = 0
        self._slot_default_counter = 0
        self.auxiliary_functions = []

    def _generate_function(self, nodes: List[TemplateNode], func_name: str, is_async: bool = False, layout_id: str = None,
                         known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None) -> str:
        """Generate a single function body."""
        def_kw = 'async def' if is_async else 'def'
        lines = [f'{def_kw} {func_name}(self):', '    parts = []', '    import json']
        
        for node in nodes:
            self._add_node(node, lines, indent=1, layout_id=layout_id, known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
            
        lines.append('    return "".join(parts)')
        return '\n'.join(lines)

    def _transform_expr(self, expr: str, local_vars: Set[str], known_globals: Set[str] = None) -> str:
        """Transform expression to use self. for non-local variables."""
        # Simple identifiers
        if expr.replace('_', '').isalnum() and not expr[0].isdigit():
            if expr in local_vars:
                return expr
            # builtins check?
            if expr in {'True', 'False', 'None'}:
                return expr
            return f'self.{expr}'

        expr = expr.strip()
        try:
            expr_ast = ast.parse(expr, mode='eval')
            
            class AddSelfTransformer(ast.NodeTransformer):
                def visit_Name(self, node):
                    import builtins
                    # Skip if builtin, local var, or KNOWN GLOBAL (import/class var)
                    if node.id not in dir(builtins) and node.id not in local_vars and (known_globals is None or node.id not in known_globals):
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
        except Exception as e:
            # Fallback regex
            def repl(m):
                word = m.group(1)
                if word in local_vars: return word
                if known_globals and word in known_globals: return word
                keywords = {'if', 'else', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None', 'for', 'while', 'await'}
                if word in keywords: return word
                
                prefix = expr[:m.start()]
                single_quotes = prefix.count("'") % 2
                double_quotes = prefix.count('"') % 2
                if single_quotes or double_quotes:
                        return word
                
                return f'self.{word}'
            
            return re.sub(r'\\b([a-zA-Z_]\w*)\\b(?!\s*[(\[])', repl, expr)

    def _transform_reactive_expr(self, expr: str, local_vars: Set[str], known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None) -> str:
        """
        Transform reactive expression. 
        - Apply self. prefix
        - Auto-call paramless methods: :foo="my_meth" -> self.my_meth()
        - Handle async: await self.my_meth()
        """
        expr = expr.strip()
        transformed = self._transform_expr(expr, local_vars, known_globals)
        
        # Check if it's a simple method reference that needs calling
        if known_methods and expr in known_methods:
             # It was transformed to self.method_name by _transform_expr
             if transformed == f"self.{expr}":
                 transformed = f"{transformed}()"
        
        # Check if we need to await async calls
        # A simple heuristic: if it contains "self.async_method(" or "self.async_method)" (end of string)
        if async_methods:
             # Basic check for now. A robust implementation would use AST.
             # But here we are operating on string that might already have 'self.'
             # Let's use AST on the transformed string to check for calls to async methods?
             # But the transformed string has 'self.', so standard ast.parse works?
             try:
                 # "self.foo()" -> Call(func=Attribute(value=Name(self), attr=foo))
                 tree = ast.parse(transformed, mode='eval')
                 class AsyncAwaiter(ast.NodeTransformer):
                     def visit_Await(self, node):
                         return node

                     def visit_Call(self, node):
                         if isinstance(node.func, ast.Attribute) and \
                            isinstance(node.func.value, ast.Name) and \
                            node.func.value.id == 'self' and \
                            node.func.attr in async_methods:
                                return ast.Await(value=node)
                         return self.generic_visit(node)
                 
                 new_tree = AsyncAwaiter().visit(tree)
                 ast.fix_missing_locations(new_tree)
                 transformed = ast.unparse(new_tree.body)
             except Exception:
                 pass

        return transformed

    def _add_node(self, node: TemplateNode, lines: List[str], indent: int = 1, local_vars: Set[str] = None, bound_var: str = None, layout_id: str = None,
                  known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None):
        if local_vars is None:
            local_vars = set()
        
        indent_str = '    ' * indent

        # 1. Handle $for
        for_attr = next((a for a in node.special_attributes if isinstance(a, ForAttribute)), None)
        if for_attr:
            loop_vars_str = for_attr.loop_vars
            new_locals = local_vars.copy()
            for var in loop_vars_str.split(','):
                new_locals.add(var.strip())
            
            iterable = self._transform_expr(for_attr.iterable, local_vars, known_globals)
            lines.append(f'{indent_str}for {loop_vars_str} in {iterable}:')
            
            new_attrs = [a for a in node.special_attributes if a is not for_attr]
            if node.tag == 'template':
                for child in node.children:
                    self._add_node(child, lines, indent + 1, new_locals, bound_var, layout_id=layout_id, known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
            else:
                new_node = replace(node, special_attributes=new_attrs)
                self._add_node(new_node, lines, indent + 1, new_locals, bound_var, layout_id=layout_id, known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
            return

        # 2. Handle $if
        if_attr = next((a for a in node.special_attributes if isinstance(a, IfAttribute)), None)
        if if_attr:
            cond = self._transform_expr(if_attr.condition, local_vars, known_globals)
            lines.append(f'{indent_str}if {cond}:')
            
            new_attrs = [a for a in node.special_attributes if a is not if_attr]
            new_node = replace(node, special_attributes=new_attrs)
            self._add_node(new_node, lines, indent + 1, local_vars, bound_var, layout_id=layout_id, known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
            return
        
        # --- Handle <slot> ---
        if node.tag == 'slot':
            slot_name = node.attributes.get('name', 'default')
            
            # Check for $head attribute (append semantics)
            is_head_slot = '$head' in node.attributes
            
            default_renderer_arg = "None"
            if node.children:
                self._slot_default_counter += 1
                func_name = f'_render_slot_default_{slot_name}_{self._slot_default_counter}'
                aux_func = self._generate_function(node.children, func_name, is_async=True)
                self.auxiliary_functions.append(aux_func)
                default_renderer_arg = f'self.{func_name}'
            
            if is_head_slot:
                lines.append(f'{indent_str}parts.append(await self.render_slot({repr(slot_name)}, default_renderer={default_renderer_arg}, layout_id={repr(layout_id)}, append=True))')
            else:
                lines.append(f'{indent_str}parts.append(await self.render_slot({repr(slot_name)}, default_renderer={default_renderer_arg}, layout_id={repr(layout_id)}))')
            return

        # 3. Render Node
        if node.tag is None:
            # Text
            if node.text_content:
                parts = self.interpolation_parser.parse(node.text_content, node.line, node.column)
                if len(parts) == 1 and isinstance(parts[0], str):
                    lines.append(f'{indent_str}parts.append({repr(node.text_content)})')
                else:
                    expr_parts = []
                    for part in parts:
                        if isinstance(part, str):
                            expr_parts.append(repr(part))
                        else:
                            transformed = self._transform_expr(part.expression, local_vars, known_globals)
                            expr_parts.append(f'str({transformed})')
                    
                    full_expr = ' + '.join(expr_parts)
                    lines.append(f'{indent_str}parts.append({full_expr})')
            else:
                for attr in node.special_attributes:
                    if isinstance(attr, InterpolationNode):
                         expr = self._transform_expr(attr.expression, local_vars, known_globals)
                         lines.append(f'{indent_str}parts.append(str({expr}))')
        else:
            # Element
            bind_attr = next((a for a in node.special_attributes if isinstance(a, BindAttribute)), None)
            bindings = {} 
            new_bound_var = bound_var 
            
            if bind_attr:
                var_name = bind_attr.variable
                self._binding_counter += 1
                handler_name = f'_handle_bind_{self._binding_counter}'
                
                tag = node.tag.lower()
                input_type = node.attributes.get('type', 'text')
                
                if tag == 'input' and input_type in ('checkbox', 'radio'):
                        event_type = 'change'
                        target_var = self._transform_expr(var_name, local_vars, known_globals)
                        bindings['checked'] = target_var 
                elif tag == 'select':
                    event_type = 'input'
                    target_var = self._transform_expr(var_name, local_vars, known_globals)
                    bindings['value'] = f'str({target_var})'
                    new_bound_var = target_var
                else:
                    event_type = 'input'
                    target_var = self._transform_expr(var_name, local_vars, known_globals)
                    bindings['value'] = f'str({target_var})'
                
                self.generated_bindings.append(BindingDef(
                    handler_name=handler_name,
                    variable_name=var_name, 
                    event_type=event_type
                ))
                bindings[f'data-on-{event_type}'] = repr(handler_name)
                
            show_attr = next((a for a in node.special_attributes if isinstance(a, ShowAttribute)), None)
            key_attr = next((a for a in node.special_attributes if isinstance(a, KeyAttribute)), None)
            if key_attr:
                bindings['id'] = f'str({self._transform_expr(key_attr.expr, local_vars, known_globals)})'

            lines.append(f'{indent_str}attrs = {{}}')
            
            for k, v in node.attributes.items():
                if '{' in v and '}' in v:
                    parts = self.interpolation_parser.parse(v, node.line, node.column)
                    expr_parts = []
                    for part in parts:
                        if isinstance(part, str):
                            expr_parts.append(repr(part))
                        else:
                            transformed = self._transform_expr(part.expression, local_vars, known_globals)
                            expr_parts.append(f'str({transformed})')
                    full_expr = ' + '.join(expr_parts)
                    lines.append(f'{indent_str}attrs[{repr(k)}] = {full_expr}')
                else:
                    lines.append(f'{indent_str}attrs[{repr(k)}] = {repr(v)}')

            for k, v in bindings.items():
                if k == 'checked':
                    lines.append(f'{indent_str}if {v}:')
                    lines.append(f'{indent_str}    attrs["checked"] = ""')
                else:
                        lines.append(f'{indent_str}attrs[{repr(k)}] = {v}')

            for attr in node.special_attributes:
                if isinstance(attr, EventAttribute):
                    lines.append(f'{indent_str}attrs["data-on-{attr.event_type}"] = {repr(attr.handler_name)}')
                    for i, arg_expr in enumerate(attr.args):
                            val = self._transform_expr(arg_expr, local_vars, known_globals)
                            lines.append(f'{indent_str}attrs["data-arg-{i}"] = json.dumps({val})')
                elif isinstance(attr, ReactiveAttribute):
                    # Transformed expression (handling async calls and self. prefix)
                    val_expr = self._transform_reactive_expr(attr.expr, local_vars, known_methods, known_globals, async_methods)
                    
                    # Store in temp var to handle reuse and checks
                    # Using a scoped block or just evaluating inline? Inline is fine if simple.
                    # Logic:
                    # if val is True (bool): attrs[name] = ""
                    # elif val is False (bool) or val is None: pass (omit)
                    # else: attrs[name] = str(val)
                    
                    # We can generate an inline if/else expression:
                    # attrs[name] = "" if (val) is True else (str(val) if (val) is not False and (val) is not None else omit)
                    # "omit" is hard in assignment.
                    # Better to generate `if` statements.
                    
                    # But if expression is complex or async, we should evaluate once.
                    lines.append(f'{indent_str}_r_val = {val_expr}')
                    
                    # Boolean attribute handling
                    # 1. HTML Boolean Attributes (presence/absence)
                    html_booleans = {'checked', 'disabled', 'selected', 'readonly', 'required', 'multiple', 'autofocus', 'novalidate', 'formnovalidate', 'hidden'}
                    
                    # 2. ARIA and other stringy booleans (true/false strings)
                    # We check for aria- prefix or specific names
                    attr_name_lower = attr.name.lower()
                    is_aria = attr_name_lower.startswith('aria-')
                    
                    if is_aria:
                        lines.append(f'{indent_str}if _r_val is True:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = "true"')
                        lines.append(f'{indent_str}elif _r_val is False:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = "false"')
                        lines.append(f'{indent_str}elif _r_val is not None:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = str(_r_val)')
                    elif attr_name_lower in html_booleans:
                        lines.append(f'{indent_str}if _r_val is True:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = ""')
                        lines.append(f'{indent_str}elif _r_val is not False and _r_val is not None:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = str(_r_val)')
                    else:
                        # Default: True -> "", False -> omit, others -> str()
                        # This covers most standard attributes where True might mean presence
                        lines.append(f'{indent_str}if _r_val is True:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = ""')
                        lines.append(f'{indent_str}elif _r_val is not False and _r_val is not None:')
                        lines.append(f'{indent_str}    attrs[{repr(attr.name)}] = str(_r_val)')

            if show_attr:
                cond = self._transform_expr(show_attr.condition, local_vars, known_globals)
                lines.append(f'{indent_str}if not {cond}:')
                lines.append(f'{indent_str}    attrs["style"] = attrs.get("style", "") + "; display: none"')
                
            if node.tag.lower() == 'option' and bound_var:
                lines.append(f'{indent_str}if "value" in attrs and str(attrs["value"]) == str({bound_var}):')
                lines.append(f'{indent_str}    attrs["selected"] = ""')

            lines.append(f'{indent_str}header_parts = []')
            lines.append(f'{indent_str}for k, v in attrs.items():')
            lines.append(f'{indent_str}    val = str(v).replace(\'"\', \'&quot;\')')
            lines.append(f'{indent_str}    header_parts.append(f\' {{k}}="{{val}}"\')')
            
            lines.append(f'{indent_str}parts.append(f"<{node.tag}{{\'\'.join(header_parts)}}>")')

            for child in node.children:
                self._add_node(child, lines, indent, local_vars, new_bound_var, layout_id=layout_id, known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)

            if node.tag.lower() not in self.VOID_ELEMENTS:
                lines.append(f'{indent_str}parts.append("</{node.tag}>")')
