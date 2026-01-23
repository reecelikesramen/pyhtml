"""Template rendering code generation."""
import ast
import re
from dataclasses import dataclass, replace
from typing import List, Set, Tuple, Dict, Optional, Union
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
    """Generates Python AST for rendering template."""

    # HTML void elements that don't have closing tags
    VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                     'link', 'meta', 'param', 'source', 'track', 'wbr', 'slot'}

    def __init__(self):
        self.interpolation_parser = JinjaInterpolationParser()
        self.generated_bindings: List[BindingDef] = []
        self._binding_counter = 0
        self._slot_default_counter = 0
        self.auxiliary_functions: List[ast.AsyncFunctionDef] = []
        self.has_file_inputs = False

    def generate_render_method(self, template_nodes: List[TemplateNode], layout_id: str = None, 
                             known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None) -> Tuple[ast.AsyncFunctionDef, List[ast.AsyncFunctionDef]]:
        """
        Generate standard _render_template method.
        Returns: (main_function_ast, list_of_auxiliary_function_asts)
        """
        self._reset_state()
        main_func = self._generate_function(template_nodes, '_render_template', is_async=True, layout_id=layout_id,
                                          known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
        return main_func, self.auxiliary_functions

    def generate_slot_methods(self, template_nodes: List[TemplateNode], file_id: str = "", known_globals: Set[str] = None, layout_id: str = None) -> Tuple[Dict[str, ast.AsyncFunctionDef], List[ast.AsyncFunctionDef]]:
        """
        Generate slot filler methods for child pages.
        Returns: ({slot_name: function_ast}, list_of_auxiliary_function_asts)
        """
        self._reset_state()
        slots = defaultdict(list)
        
        # Generate a short hash from file_id to make method names unique per file
        import hashlib
        file_hash = hashlib.md5(file_id.encode()).hexdigest()[:8] if file_id else ""
        
        # 1. Bucket nodes into slots based on wrapper elements
        for node in template_nodes:
            if node.tag == 'slot' and node.attributes and 'name' in node.attributes:
                slot_name = node.attributes['name']
                for child in node.children:
                    slots[slot_name].append(child)
            elif node.tag == 'pyhtml-head':
                for child in node.children:
                    slots['$head'].append(child)
            else:
                slots['default'].append(node)
            
        # 2. Generate functions for each slot
        slot_funcs = {}
        for slot_name, nodes in slots.items():
            safe_name = slot_name.replace('$', '_head_').replace('-', '_') if slot_name.startswith('$') else slot_name.replace('-', '_')
            func_name = f'_render_slot_fill_{safe_name}_{file_hash}' if file_hash else f'_render_slot_fill_{safe_name}'
            slot_funcs[slot_name] = self._generate_function(nodes, func_name, is_async=True, known_globals=known_globals, layout_id=layout_id)
            
        return slot_funcs, self.auxiliary_functions

    def _reset_state(self):
        self.generated_bindings = []
        self._binding_counter = 0
        self._slot_default_counter = 0
        self.auxiliary_functions = []
        self.has_file_inputs = False

    def _generate_function(self, nodes: List[TemplateNode], func_name: str, is_async: bool = False, layout_id: str = None,
                         known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None) -> ast.AsyncFunctionDef:
        """Generate a single function body as AST."""
        
        # parts = []
        body: List[ast.stmt] = [
            ast.Assign(
                targets=[ast.Name(id='parts', ctx=ast.Store())],
                value=ast.List(elts=[], ctx=ast.Load())
            ),
            # import json (for attribute serialization)
            ast.Import(names=[ast.alias(name='json', asname=None)])
        ]
        
        for node in nodes:
            self._add_node(node, body, layout_id=layout_id, known_methods=known_methods, known_globals=known_globals, async_methods=async_methods)
            
        # return "".join(parts)
        body.append(
            ast.Return(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Constant(value=''), attr='join', ctx=ast.Load()),
                    args=[ast.Name(id='parts', ctx=ast.Load())],
                    keywords=[]
                )
            )
        )
        
        func_def = ast.AsyncFunctionDef(
            name=func_name,
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg='self')],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=body,
            decorator_list=[],
            returns=None
        )
        # We don't set lineno on the function def itself as it's generated, 
        # but we could set it to the first node's line? 
        # Better to leave it (defaults to 1?) or set to 0. 
        # The body statements will have correct linenos.
        return func_def

    def _transform_expr(self, expr_str: str, local_vars: Set[str], known_globals: Set[str] = None, line_offset: int = 0, col_offset: int = 0) -> ast.expr:
        """Transform expression string to AST with self. handling."""
        expr_str = expr_str.strip()
        
        try:
            tree = ast.parse(expr_str, mode='eval')
            if line_offset > 0:
                # ast.increment_lineno uses 1-based indexing for AST, but adds diff
                # We want result to be line_offset.
                # Current starts at 1.
                # diff = line_offset - 1
                ast.increment_lineno(tree, line_offset - 1)
        except SyntaxError:
            # Fallback for complex/invalid syntax (legacy support)
            # Try regex replacement then parse
            def repl(m):
                word = m.group(1)
                if word in local_vars: return word
                if known_globals and word in known_globals: return word
                keywords = {'if', 'else', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None'}
                if word in keywords: return word
                return f'self.{word}'
            
            replaced = re.sub(r'\\b([a-zA-Z_]\w*)\\b(?!\s*[(\[])', repl, expr_str)
            tree = ast.parse(replaced, mode='eval')

        class AddSelfTransformer(ast.NodeTransformer):
            def visit_Name(self, node):
                import builtins
                if node.id not in dir(builtins) and node.id not in local_vars and (known_globals is None or node.id not in known_globals):
                    return ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=node.id,
                        ctx=node.ctx
                    )
                return node
        
        new_tree = AddSelfTransformer().visit(tree)
        # Returns the expression node
        return new_tree.body

    def _transform_reactive_expr(self, expr_str: str, local_vars: Set[str], known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None, line_offset: int = 0, col_offset: int = 0) -> ast.expr:
        """Transform reactive expression to AST, handling async calls and self."""
        base_expr = self._transform_expr(expr_str, local_vars, known_globals, line_offset, col_offset)
        
        # Auto-call if it matches self.method
        if isinstance(base_expr, ast.Attribute) and isinstance(base_expr.value, ast.Name) and base_expr.value.id == 'self':
             if known_methods and base_expr.attr in known_methods:
                 base_expr = ast.Call(func=base_expr, args=[], keywords=[])
        
        # Async handling
        if async_methods:
            class AsyncAwaiter(ast.NodeTransformer):
                def __init__(self):
                    self.in_await = False

                def visit_Await(self, node):
                    self.in_await = True
                    self.generic_visit(node)
                    self.in_await = False
                    return node

                def visit_Call(self, node):
                    # Check if already awaited
                    if self.in_await:
                        return self.generic_visit(node)

                    if isinstance(node.func, ast.Attribute) and \
                       isinstance(node.func.value, ast.Name) and \
                       node.func.value.id == 'self' and \
                       node.func.attr in async_methods:
                        return ast.Await(value=node)
                    return self.generic_visit(node)
            
            # Wrap in Module/Expr to visit
            mod = ast.Module(body=[ast.Expr(value=base_expr)], type_ignores=[])
            AsyncAwaiter().visit(mod)
            base_expr = mod.body[0].value
            
        return base_expr

    def _set_line(self, node: ast.AST, template_node: TemplateNode):
        """Helper to set line number on AST node."""
        if template_node.line > 0:
            node.lineno = template_node.line
            node.col_offset = template_node.column
            node.end_lineno = template_node.line  # Single line approximation
            node.end_col_offset = template_node.column + 1
        return node

    def _add_node(self, node: TemplateNode, body: List[ast.stmt], local_vars: Set[str] = None, bound_var: str = None, layout_id: str = None,
                  known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None):
        if local_vars is None:
            local_vars = set()

        # 1. Handle $for
        for_attr = next((a for a in node.special_attributes if isinstance(a, ForAttribute)), None)
        if for_attr:
            loop_vars_str = for_attr.loop_vars
            new_locals = local_vars.copy()
            
            # Parse loop vars to handle tuple unpacking
            # "x, y" -> targets
            loop_targets_node = ast.parse(f"{loop_vars_str} = 1").body[0].targets[0]
            
            def extract_names(n):
                if isinstance(n, ast.Name):
                    new_locals.add(n.id)
                elif isinstance(n, (ast.Tuple, ast.List)):
                    for elt in n.elts:
                        extract_names(elt)
            extract_names(loop_targets_node)

            iterable_expr = self._transform_expr(for_attr.iterable, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
            
            for_body = []
            
            new_attrs = [a for a in node.special_attributes if a is not for_attr]
            if node.tag == 'template':
                for child in node.children:
                    self._add_node(child, for_body, new_locals, bound_var, layout_id, known_methods, known_globals, async_methods)
            else:
                new_node = replace(node, special_attributes=new_attrs)
                self._add_node(new_node, for_body, new_locals, bound_var, layout_id, known_methods, known_globals, async_methods)
            
            for_stmt = ast.AsyncFor(
                target=loop_targets_node,
                iter=iterable_expr,
                body=for_body,
                orelse=[]
            )
            # Tag with line number
            self._set_line(for_stmt, node)
            body.append(for_stmt)
            return

        # 2. Handle $if
        if_attr = next((a for a in node.special_attributes if isinstance(a, IfAttribute)), None)
        if if_attr:
            cond_expr = self._transform_expr(if_attr.condition, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
            
            if_body = []
            new_attrs = [a for a in node.special_attributes if a is not if_attr]
            new_node = replace(node, special_attributes=new_attrs)
            self._add_node(new_node, if_body, local_vars, bound_var, layout_id, known_methods, known_globals, async_methods)
            
            if_stmt = ast.If(
                test=cond_expr,
                body=if_body,
                orelse=[]
            )
            self._set_line(if_stmt, node)
            body.append(if_stmt)
            return
        
        # --- Handle <slot> ---
        if node.tag == 'slot':
            slot_name = node.attributes.get('name', 'default')
            is_head_slot = '$head' in node.attributes
            
            default_renderer_arg = ast.Constant(value=None)
            if node.children:
                self._slot_default_counter += 1
                func_name = f'_render_slot_default_{slot_name}_{self._slot_default_counter}'
                aux_func = self._generate_function(node.children, func_name, is_async=True)
                self.auxiliary_functions.append(aux_func)
                default_renderer_arg = ast.Attribute(
                    value=ast.Name(id='self', ctx=ast.Load()),
                    attr=func_name,
                    ctx=ast.Load()
                )
            
            call_kwargs = [
                ast.keyword(arg='default_renderer', value=default_renderer_arg),
                ast.keyword(arg='layout_id', value=ast.Constant(value=layout_id))
            ]
            if is_head_slot:
                call_kwargs.append(ast.keyword(arg='append', value=ast.Constant(value=True)))

            render_call = ast.Call(
                func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='render_slot', ctx=ast.Load()),
                args=[ast.Constant(value=slot_name)],
                keywords=call_kwargs
            )
            
            append_stmt = ast.Expr(value=ast.Call(
                func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                args=[ast.Await(value=render_call)],
                keywords=[]
            ))
            self._set_line(append_stmt, node)
            body.append(append_stmt)
            return

        # 3. Render Node
        if node.tag is None:
            # Text
            if node.text_content:
                parts = self.interpolation_parser.parse(node.text_content, node.line, node.column)
                if len(parts) == 1 and isinstance(parts[0], str):
                    append_stmt = ast.Expr(value=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                        args=[ast.Constant(value=node.text_content)],
                        keywords=[]
                    ))
                    self._set_line(append_stmt, node)
                    body.append(append_stmt)
                else:
                    # Construct concatenation: str(part1) + str(part2) ...
                    # Or just parts.append(str(p1) + str(p2))
                    # Wait, cleaner to append individually?
                    # "parts.append(a + b)" is what old code did.
                    
                    current_concat = None
                    
                    for part in parts:
                        if isinstance(part, str):
                            term = ast.Constant(value=part)
                        else:
                            term = ast.Call(
                                func=ast.Name(id='str', ctx=ast.Load()),
                                args=[self._transform_expr(part.expression, local_vars, known_globals, line_offset=part.line, col_offset=part.column)],
                                keywords=[]
                            )
                        
                        if current_concat is None:
                            current_concat = term
                        else:
                            current_concat = ast.BinOp(left=current_concat, op=ast.Add(), right=term)
                            
                    if current_concat:
                        append_stmt = ast.Expr(value=ast.Call(
                            func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                            args=[current_concat],
                            keywords=[]
                        ))
                        self._set_line(append_stmt, node)
                        body.append(append_stmt)
            else:
                for attr in node.special_attributes:
                    if isinstance(attr, InterpolationNode):
                         expr = self._transform_expr(attr.expression, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
                         append_stmt = ast.Expr(value=ast.Call(
                            func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                            args=[ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[expr], keywords=[])],
                            keywords=[]
                         ))
                         self._set_line(append_stmt, node)
                         body.append(append_stmt)
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
                
                if tag == 'input' and input_type == 'file':
                     self.has_file_inputs = True
                
                if bind_attr.binding_type == 'progress':
                    self.generated_bindings.append(BindingDef(handler_name, var_name, 'upload-progress'))
                    bindings['data-on-upload-progress'] = ast.Constant(value=handler_name)
                    
                else:
                    event_type = 'input'
                    val_prop = 'value'
                    
                    if tag == 'input' and input_type in ('checkbox', 'radio'):
                         event_type = 'change'
                         val_prop = 'checked'
                    
                    target_var_expr = self._transform_expr(var_name, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
                    
                    bindings[val_prop] = target_var_expr
                    if tag == 'select': 
                        new_bound_var = target_var_expr # AST node passed as bound_var? No, logic expects expr
                        # But bound_var is passed recursively.
                        # Wait, logic for <option> uses bound_var which is currently a string in old code?
                        # "if str(attrs['value']) == str({bound_var}):"
                        # We need to pass the expression object or similar?
                        # Let's pass the AST expression node.
                        new_bound_var = target_var_expr

                    self.generated_bindings.append(BindingDef(handler_name, var_name, event_type))
                    bindings[f'data-on-{event_type}'] = ast.Constant(value=handler_name)


            show_attr = next((a for a in node.special_attributes if isinstance(a, ShowAttribute)), None)
            key_attr = next((a for a in node.special_attributes if isinstance(a, KeyAttribute)), None)
            
            if key_attr:
                bindings['id'] = ast.Call(
                    func=ast.Name(id='str', ctx=ast.Load()),
                    args=[self._transform_expr(key_attr.expr, local_vars, known_globals, line_offset=node.line, col_offset=node.column)],
                    keywords=[]
                )

            # attrs = {}
            body.append(ast.Assign(
                targets=[ast.Name(id='attrs', ctx=ast.Store())],
                value=ast.Dict(keys=[], values=[])
            ))
            
            # Static attrs
            for k, v in node.attributes.items():
                if '{' in v and '}' in v:
                    parts = self.interpolation_parser.parse(v, node.line, node.column)
                    current_concat = None
                    for part in parts:
                        if isinstance(part, str):
                            term = ast.Constant(value=part)
                        else:
                            term = ast.Call(
                                func=ast.Name(id='str', ctx=ast.Load()),
                                args=[self._transform_expr(part.expression, local_vars, known_globals)],
                                keywords=[]
                            )
                        if current_concat is None: current_concat = term
                        else: current_concat = ast.BinOp(left=current_concat, op=ast.Add(), right=term)
                    
                    val_expr = current_concat if current_concat else ast.Constant(value="")
                else:
                    val_expr = ast.Constant(value=v)
                
                body.append(ast.Assign(
                    targets=[ast.Subscript(
                        value=ast.Name(id='attrs', ctx=ast.Load()),
                        slice=ast.Constant(value=k),
                        ctx=ast.Store()
                    )],
                    value=val_expr
                ))

            # Bindings
            for k, v in bindings.items():
                if k == 'checked':
                     # if v: attrs['checked'] = ""
                     body.append(ast.If(
                         test=v,
                         body=[ast.Assign(
                             targets=[ast.Subscript(
                                 value=ast.Name(id='attrs', ctx=ast.Load()),
                                 slice=ast.Constant(value='checked'),
                                 ctx=ast.Store()
                             )],
                             value=ast.Constant(value="")
                         )],
                         orelse=[]
                     ))
                else:
                    # attrs[k] = str(v) usually? 
                    # If v is AST expression (from target_var_expr), wrap in str()
                    # If v is Constant string, direct.
                    # Warning: bindings[k] contains AST nodes now.
                    
                    wrapper = v
                    if not isinstance(v, ast.Constant):
                        wrapper = ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[v], keywords=[])
                    
                    body.append(ast.Assign(
                        targets=[ast.Subscript(
                            value=ast.Name(id='attrs', ctx=ast.Load()),
                            slice=ast.Constant(value=k),
                            ctx=ast.Store()
                        )],
                        value=wrapper
                    ))


            # Group and generate event attributes (handling multiples via JSON)
            event_attrs_by_type = defaultdict(list)
            for attr in node.special_attributes:
                if isinstance(attr, EventAttribute):
                    event_attrs_by_type[attr.event_type].append(attr)
            
            for event_type, attrs_list in event_attrs_by_type.items():
                if len(attrs_list) == 1:
                    # Single handler
                    attr = attrs_list[0]
                    # attrs["data-on-X"] = "handler"
                    body.append(ast.Assign(
                        targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=f'data-on-{event_type}'), ctx=ast.Store())],
                        value=ast.Constant(value=attr.handler_name)
                    ))
                    
                    # Add modifiers if present
                    if attr.modifiers:
                        modifiers_str = " ".join(attr.modifiers)
                        body.append(ast.Assign(
                            targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=f'data-modifiers-{event_type}'), ctx=ast.Store())],
                            value=ast.Constant(value=modifiers_str)
                        ))
                    
                    # Add args
                    for i, arg_expr in enumerate(attr.args):
                        val = self._transform_expr(arg_expr, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
                        dump_call = ast.Call(
                            func=ast.Attribute(value=ast.Name(id='json', ctx=ast.Load()), attr='dumps', ctx=ast.Load()),
                            args=[val], keywords=[]
                        )
                        body.append(ast.Assign(
                            targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=f'data-arg-{i}'), ctx=ast.Store())],
                            value=dump_call
                        ))
                else:
                    # Multiple handlers - JSON format
                    # _handlers_X = []
                    handler_list_name = f'_handlers_{event_type}'
                    body.append(ast.Assign(
                        targets=[ast.Name(id=handler_list_name, ctx=ast.Store())],
                        value=ast.List(elts=[], ctx=ast.Load())
                    ))
                    
                    all_modifiers = set()
                    for attr in attrs_list:
                        modifiers = attr.modifiers or []
                        all_modifiers.update(modifiers)
                        
                        # _h = {"handler": "...", "modifiers": [...]}
                        handler_dict = ast.Dict(
                            keys=[ast.Constant(value="handler"), ast.Constant(value="modifiers")],
                            values=[ast.Constant(value=attr.handler_name), ast.List(elts=[ast.Constant(value=m) for m in modifiers], ctx=ast.Load())]
                        )
                        body.append(ast.Assign(
                            targets=[ast.Name(id='_h', ctx=ast.Store())],
                            value=handler_dict
                        ))
                        
                        if attr.args:
                            # _args = [...]
                            args_list = []
                            for arg_expr in attr.args:
                                val = self._transform_expr(arg_expr, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
                                args_list.append(val)
                            body.append(ast.Assign(
                                targets=[ast.Subscript(value=ast.Name(id='_h', ctx=ast.Load()), slice=ast.Constant(value="args"), ctx=ast.Store())],
                                value=ast.List(elts=args_list, ctx=ast.Load())
                            ))
                        
                        # _handlers_X.append(_h)
                        body.append(ast.Expr(value=ast.Call(
                            func=ast.Attribute(value=ast.Name(id=handler_list_name, ctx=ast.Load()), attr='append', ctx=ast.Load()),
                            args=[ast.Name(id='_h', ctx=ast.Load())],
                            keywords=[]
                        )))
                    
                    # attrs["data-on-X"] = json.dumps(_handlers_X)
                    body.append(ast.Assign(
                        targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=f'data-on-{event_type}'), ctx=ast.Store())],
                        value=ast.Call(
                            func=ast.Attribute(value=ast.Name(id='json', ctx=ast.Load()), attr='dumps', ctx=ast.Load()),
                            args=[ast.Name(id=handler_list_name, ctx=ast.Load())],
                            keywords=[]
                        )
                    ))
                    
                    if all_modifiers:
                        modifiers_str = " ".join(all_modifiers)
                        body.append(ast.Assign(
                            targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=f'data-modifiers-{event_type}'), ctx=ast.Store())],
                            value=ast.Constant(value=modifiers_str)
                        ))

            # Handle other special attributes
            for attr in node.special_attributes:
                if isinstance(attr, EventAttribute):
                    continue
                elif isinstance(attr, ReactiveAttribute):
                    val_expr = self._transform_reactive_expr(attr.expr, local_vars, known_methods, known_globals, async_methods, line_offset=node.line, col_offset=node.column)
                    
                    # _r_val = val_expr
                    body.append(ast.Assign(
                        targets=[ast.Name(id='_r_val', ctx=ast.Store())],
                        value=val_expr
                    ))
                    
                    html_booleans = {'checked', 'disabled', 'selected', 'readonly', 'required', 'multiple', 'autofocus', 'novalidate', 'formnovalidate', 'hidden'}
                    is_aria = attr.name.lower().startswith('aria-')
                    is_bool = attr.name.lower() in html_booleans

                    if is_aria:
                        # if _r_val is True: attrs["X"] = "true"
                        # elif _r_val is False: attrs["X"] = "false"
                        # elif _r_val is not None: attrs["X"] = str(_r_val)
                        
                        body.append(ast.If(
                            test=ast.Compare(left=ast.Name(id='_r_val', ctx=ast.Load()), ops=[ast.Is()], comparators=[ast.Constant(value=True)]),
                            body=[ast.Assign(targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=attr.name), ctx=ast.Store())], value=ast.Constant(value="true"))],
                            orelse=[ast.If(
                                test=ast.Compare(left=ast.Name(id='_r_val', ctx=ast.Load()), ops=[ast.Is()], comparators=[ast.Constant(value=False)]),
                                body=[ast.Assign(targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=attr.name), ctx=ast.Store())], value=ast.Constant(value="false"))],
                                orelse=[ast.If(
                                    test=ast.Compare(left=ast.Name(id='_r_val', ctx=ast.Load()), ops=[ast.IsNot()], comparators=[ast.Constant(value=None)]),
                                    body=[ast.Assign(targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=attr.name), ctx=ast.Store())], value=ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[ast.Name(id='_r_val', ctx=ast.Load())], keywords=[]))],
                                    orelse=[]
                                )]
                            )]
                        ))
                    else:
                        # Default bool behavior
                        # if _r_val is True: attrs["X"] = ""
                        # elif _r_val is not False and _r_val is not None: attrs["X"] = str(_r_val)
                        
                        body.append(ast.If(
                            test=ast.Compare(left=ast.Name(id='_r_val', ctx=ast.Load()), ops=[ast.Is()], comparators=[ast.Constant(value=True)]),
                            body=[ast.Assign(targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=attr.name), ctx=ast.Store())], value=ast.Constant(value=""))],
                            orelse=[ast.If(
                                test=ast.BoolOp(op=ast.And(), values=[
                                    ast.Compare(left=ast.Name(id='_r_val', ctx=ast.Load()), ops=[ast.IsNot()], comparators=[ast.Constant(value=False)]),
                                    ast.Compare(left=ast.Name(id='_r_val', ctx=ast.Load()), ops=[ast.IsNot()], comparators=[ast.Constant(value=None)])
                                ]),
                                body=[ast.Assign(targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value=attr.name), ctx=ast.Store())], value=ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[ast.Name(id='_r_val', ctx=ast.Load())], keywords=[]))],
                                orelse=[]
                            )]
                        ))

            if show_attr:
                cond = self._transform_expr(show_attr.condition, local_vars, known_globals, line_offset=node.line, col_offset=node.column)
                # if not cond: attrs['style'] = ...
                body.append(ast.If(
                    test=ast.UnaryOp(op=ast.Not(), operand=cond),
                    body=[
                        ast.Assign(
                            targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value='style'), ctx=ast.Store())],
                            value=ast.BinOp(
                                left=ast.Call(
                                    func=ast.Attribute(value=ast.Name(id='attrs', ctx=ast.Load()), attr='get', ctx=ast.Load()),
                                    args=[ast.Constant(value='style'), ast.Constant(value='')], keywords=[]
                                ),
                                op=ast.Add(),
                                right=ast.Constant(value='; display: none')
                            )
                        )
                    ],
                    orelse=[]
                ))

            if node.tag.lower() == 'option' and bound_var:
                # if "value" in attrs and str(attrs["value"]) == str(bound_var): attrs["selected"] = ""
                # bound_var is AST node here
                # We need to reuse bound_var AST node carefully (if it's complex, it might be evaluated multiple times, but usually it's just Name or Attribute)
                
                check = ast.If(
                    test=ast.BoolOp(op=ast.And(), values=[
                        ast.Compare(left=ast.Constant(value='value'), ops=[ast.In()], comparators=[ast.Name(id='attrs', ctx=ast.Load())]),
                        ast.Compare(
                            left=ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value='value'), ctx=ast.Load())], keywords=[]),
                            ops=[ast.Eq()],
                            comparators=[ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[bound_var], keywords=[])]
                        )
                    ]),
                    body=[ast.Assign(
                        targets=[ast.Subscript(value=ast.Name(id='attrs', ctx=ast.Load()), slice=ast.Constant(value='selected'), ctx=ast.Store())],
                        value=ast.Constant(value="")
                    )],
                    orelse=[]
                )
                body.append(check)

            # Generate opening tag
            # header_parts = [] ...
            # parts.append(f"<{tag}{''.join(header_parts)}>")
            
            # header_parts = [f' {k}="{str(v).replace('"', '&quot;')}"' for k,v in attrs.items()]
            # This logic is complex to AST-ify directly in one loop.
            # Use runtime loop? "for k, v in attrs.items(): ..."
            
            # parts.append(f"<{node.tag}")
            body.append(ast.Expr(value=ast.Call(
                 func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                 args=[ast.Constant(value=f"<{node.tag}")],
                 keywords=[]
            )))
            
            # Runtime loop to append attributes
            # for k, v in attrs.items():
            #     val = str(v).replace('"', '&quot;')
            #     parts.append(f' {k}="{val}"')
            
            attr_loop = ast.For(
                target=ast.Tuple(elts=[ast.Name(id='k', ctx=ast.Store()), ast.Name(id='v', ctx=ast.Store())], ctx=ast.Store()),
                iter=ast.Call(func=ast.Attribute(value=ast.Name(id='attrs', ctx=ast.Load()), attr='items', ctx=ast.Load()), args=[], keywords=[]),
                body=[
                    ast.Assign(
                        targets=[ast.Name(id='val', ctx=ast.Store())],
                        value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[ast.Name(id='v', ctx=ast.Load())], keywords=[]),
                                attr='replace',
                                ctx=ast.Load()
                            ),
                            args=[ast.Constant(value='"'), ast.Constant(value='&quot;')],
                            keywords=[]
                        )
                    ),
                    ast.Expr(value=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                        args=[ast.JoinedStr(values=[
                            ast.Constant(value=' '),
                            ast.FormattedValue(value=ast.Name(id='k', ctx=ast.Load()), conversion=-1),
                            ast.Constant(value='="'),
                            ast.FormattedValue(value=ast.Name(id='val', ctx=ast.Load()), conversion=-1),
                            ast.Constant(value='"')
                        ])],
                        keywords=[]
                    ))
                ],
                orelse=[]
            )
            body.append(attr_loop)
            
            # Close opening tag
            body.append(ast.Expr(value=ast.Call(
                 func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                 args=[ast.Constant(value=">")],
                 keywords=[]
            )))

            for child in node.children:
                self._add_node(child, body, local_vars, new_bound_var, layout_id, known_methods, known_globals, async_methods)

            if node.tag.lower() not in self.VOID_ELEMENTS:
                body.append(ast.Expr(value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()),
                    args=[ast.Constant(value=f"</{node.tag}>")],
                    keywords=[]
                )))
