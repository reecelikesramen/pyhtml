"""Main code generator orchestrator."""
import ast
from typing import Dict, List, Type, Tuple, Set, Optional

from pyhtml.compiler.ast_nodes import Directive, ParsedPyHTML, PathDirective, NoSpaDirective, SpecialAttribute, EventAttribute
from pyhtml.compiler.codegen.attributes.base import AttributeCodegen
from pyhtml.compiler.codegen.attributes.events import EventAttributeCodegen
from pyhtml.compiler.codegen.directives.base import DirectiveCodegen
from pyhtml.compiler.codegen.directives.path import PathDirectiveCodegen
from pyhtml.compiler.codegen.template import TemplateCodegen


class CodeGenerator:
    """Generates Python module from ParsedPyHTML AST."""

    def __init__(self):
        self.directive_handlers: Dict[Type[Directive], DirectiveCodegen] = {
            PathDirective: PathDirectiveCodegen(),
            # Future: LayoutDirective: LayoutDirectiveCodegen(), etc.
        }

        self.attribute_handlers: Dict[Type[SpecialAttribute], AttributeCodegen] = {
            EventAttribute: EventAttributeCodegen(),
            # Future: BindAttribute: BindAttributeCodegen(), etc.
        }

        self.template_codegen = TemplateCodegen()

    def generate(self, parsed: ParsedPyHTML) -> ast.Module:
        """Generate complete module AST."""
        module_body = []

        # Imports
        module_body.extend(self._generate_imports())
        
        # Add asyncio import for handle_event
        module_body.append(
            ast.Import(names=[ast.alias(name='asyncio', asname=None)])
        )

        # Extract user imports from Python section
        if parsed.python_ast:
            module_body.extend(self._extract_user_imports(parsed.python_ast))

        # Extract method names early for binding logic
        known_methods = self._collect_method_names(parsed.python_ast)
        
        # Inline handlers (with method names)
        handlers = self._extract_inline_handlers(parsed, known_methods)
        
        # Page class
        page_class = self._generate_page_class(parsed, handlers)
        module_body.append(page_class)

        module = ast.Module(body=module_body, type_ignores=[])
        ast.fix_missing_locations(module)
        return module

    def _generate_imports(self) -> List[ast.stmt]:
        """Generate framework imports."""
        return [
            ast.ImportFrom(
                module='pyhtml.runtime.page',
                names=[ast.alias(name='BasePage', asname=None)],
                level=0
            ),
            ast.ImportFrom(
                module='starlette.responses',
                names=[ast.alias(name='Response', asname=None)],
                level=0
            ),
            ast.Import(names=[ast.alias(name='json', asname=None)]),
        ]

    def _extract_user_imports(self, python_ast: ast.Module) -> List[ast.stmt]:
        """Extract import statements from user Python code."""
        imports = []
        for node in python_ast.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
        return imports

    def _generate_page_class(self, parsed: ParsedPyHTML, handlers: List[ast.AsyncFunctionDef]) -> ast.ClassDef:
        """Generate page class definition."""
        class_body = []
        
        # Add generated handlers
        class_body.extend(handlers)

        # Generate directive assignments (e.g., __routes__)
        for directive in parsed.directives:
            handler = self.directive_handlers.get(type(directive))
            if handler:
                class_body.extend(handler.generate(directive))

        # Generate SPA navigation metadata
        class_body.extend(self._generate_spa_metadata(parsed))

        # Generate __init__ method
        class_body.append(self._generate_init_method(parsed))

        # Transform user Python code to class methods
        # Transform user Python code to class methods
        if parsed.python_ast:
            class_body.extend(self._transform_user_code(parsed.python_ast))

        # Generate render method
        class_body.append(self._generate_render_method())



        # Generate _render_template method AND binding methods
        render_func, binding_funcs = self._generate_render_template_method(parsed)
        class_body.append(render_func)
        class_body.extend(binding_funcs)

        # Generate handle_event method
        class_body.append(self._generate_handle_event_method())

        cls_def = ast.ClassDef(
            name=self._get_class_name(parsed),
            bases=[ast.Name(id='BasePage', ctx=ast.Load())],
            keywords=[],
            body=class_body,
            decorator_list=[]
        )
        cls_def.lineno = 1
        cls_def.col_offset = 0
        return cls_def

    def _collect_method_names(self, python_ast: Optional[ast.Module]) -> Set[str]:
        """Collect defined function names."""
        names = set()
        if python_ast:
            for node in python_ast.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(node.name)
        return names

    def _extract_inline_handlers(self, parsed: ParsedPyHTML, known_methods: Set[str]) -> List[ast.AsyncFunctionDef]:
        """Extract inline handlers to methods, lifting arguments."""
        handlers = []
        handler_count = 0
        from pyhtml.compiler.ast_nodes import EventAttribute

        def visit_nodes(nodes):
            nonlocal handler_count
            for node in nodes:
                for attr in node.special_attributes:
                    if isinstance(attr, EventAttribute):
                        if not attr.handler_name.isidentifier():
                            # Inline code - needs transformation
                            method_name = f'_handler_{handler_count}'
                            handler_count += 1
                            
                            try:
                                body, args = self._transform_inline_code(attr.handler_name, known_methods)
                                
                                # Store extracted args for template rendering
                                attr.args = args
                                
                                # Create handler method
                                # async def _handler_X(self, arg0, arg1...):
                                arg_definitions = [ast.arg(arg='self')]
                                for i in range(len(args)):
                                    arg_definitions.append(ast.arg(arg=f'arg{i}'))

                                handlers.append(ast.AsyncFunctionDef(
                                    name=method_name,
                                    args=ast.arguments(
                                        posonlyargs=[],
                                        args=arg_definitions,
                                        vararg=None,
                                        kwonlyargs=[],
                                        kw_defaults=[],
                                        defaults=[]
                                    ),
                                    body=body,
                                    decorator_list=[],
                                    returns=None
                                ))
                                
                                attr.handler_name = method_name
                                
                            except Exception as e:
                                print(f"Error compiling inline handler '{attr.handler_name}': {e}")
                
                visit_nodes(node.children)

        visit_nodes(parsed.template)
        return handlers

    def _transform_inline_code(self, code: str, known_methods: Set[str] = None) -> Tuple[List[ast.stmt], List[str]]:
        """Transform inline code: lift arguments and prefix globals with self."""
        import builtins
        
        tree = ast.parse(code)
        extracted_args = []
        
        class ArgumentLifter(ast.NodeTransformer):
            def visit_Call(self, node):
                # Check arguments for unbound variables
                new_args = []
                for arg in node.args:
                    # Quick check: does this arg contain unbound names?
                    unbound = False
                    for child in ast.walk(arg):
                         if isinstance(child, ast.Name):
                             if child.id not in known_methods and child.id not in dir(builtins):
                                 unbound = True
                                 break
                    
                    if unbound:
                        # Lift it!
                        arg_index = len(extracted_args)
                        extracted_args.append(ast.unparse(arg))
                        new_args.append(ast.Name(id=f'arg{arg_index}', ctx=ast.Load()))
                    else:
                        new_args.append(self.visit(arg))
                
                node.args = new_args
                return self.generic_visit(node)
                
            def visit_Name(self, node):
                # Transform known methods and globals to self.X
                if node.id in known_methods:
                     return ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=node.id,
                        ctx=node.ctx
                    )
                return node

        # Run transformer
        transformer = ArgumentLifter()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        
        return new_tree.body, extracted_args

        # Transform
        SelfTransformer().visit(tree)
        
        if async_methods:
            class AsyncCallTransformer(ast.NodeTransformer):
                def visit_Call(self, node):
                    # Check if call to self.async_method
                    # The func is now (after SelfTransformer) self.method_name
                    if isinstance(node.func, ast.Attribute) and \
                       isinstance(node.func.value, ast.Name) and \
                       node.func.value.id == 'self' and \
                       node.func.attr in async_methods:
                        return ast.Await(value=node)
                    return node
            
            AsyncCallTransformer().visit(tree)

        ast.fix_missing_locations(tree)
        return tree.body

    def _generate_spa_metadata(self, parsed: ParsedPyHTML) -> List[ast.stmt]:
        """Generate __spa_enabled__ and __sibling_paths__ class attributes."""
        stmts = []
        
        # Get path directive
        path_directive = parsed.get_directive_by_type(PathDirective)
        is_multi_path = path_directive and not path_directive.is_simple_string
        
        # Check for !no_spa directive
        no_spa = parsed.get_directive_by_type(NoSpaDirective) is not None
        
        # SPA is enabled for multi-path pages unless !no_spa is present
        spa_enabled = is_multi_path and not no_spa
        
        # __spa_enabled__ = True/False
        stmts.append(ast.Assign(
            targets=[ast.Name(id='__spa_enabled__', ctx=ast.Store())],
            value=ast.Constant(value=spa_enabled)
        ))
        
        # __sibling_paths__ = ['/path1', '/path2', ...]
        if path_directive and not path_directive.is_simple_string:
            paths = list(path_directive.routes.values())
        else:
            paths = []
        
        stmts.append(ast.Assign(
            targets=[ast.Name(id='__sibling_paths__', ctx=ast.Store())],
            value=ast.List(
                elts=[ast.Constant(value=p) for p in paths],
                ctx=ast.Load()
            )
        ))
        
        # Inject __file_path__ for hot reload route cleanup
        if parsed.file_path:
             stmts.append(ast.Assign(
                targets=[ast.Name(id='__file_path__', ctx=ast.Store())],
                value=ast.Constant(value=str(parsed.file_path))
            ))
        
        return stmts

    def _get_class_name(self, parsed: ParsedPyHTML) -> str:
        """Generate class name from file path."""
        if not parsed.file_path:
            return 'Page'
        
        from pathlib import Path
        path = Path(parsed.file_path)
        # Convert pages/index.pyhtml -> IndexPage
        name = path.stem
        return ''.join(word.capitalize() for word in name.split('_')) + 'Page'

    def _generate_init_method(self, parsed: ParsedPyHTML) -> ast.FunctionDef:
        """Generate __init__ method."""
        return ast.FunctionDef(
            name='__init__',
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg='self'),
                    ast.arg(arg='request'),
                    ast.arg(arg='params'),
                    ast.arg(arg='query'),
                    ast.arg(arg='path'),
                    ast.arg(arg='url')
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[ast.Constant(value=None), ast.Constant(value=None)]
            ),
            body=[
                ast.Expr(value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Call(
                            func=ast.Name(id='super', ctx=ast.Load()),
                            args=[],
                            keywords=[]
                        ),
                        attr='__init__',
                        ctx=ast.Load()
                    ),
                    args=[
                        ast.Name(id='request', ctx=ast.Load()),
                        ast.Name(id='params', ctx=ast.Load()),
                        ast.Name(id='query', ctx=ast.Load()),
                        ast.Name(id='path', ctx=ast.Load()),
                        ast.Name(id='url', ctx=ast.Load())
                    ],
                    keywords=[]
                ))
            ],
            decorator_list=[],
            returns=None
        )

    def _transform_user_code(self, python_ast: ast.Module) -> List[ast.stmt]:
        """Transform user Python code to class methods/attributes."""
        transformed = []
        
        # Collect all method names to treat them as 'globals' (attributes of self)
        method_names = set()
        for node in python_ast.body:
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                 method_names.add(node.name)

        for node in python_ast.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Skip imports - already handled
                continue
            elif isinstance(node, ast.Assign):
                # Module-level assignments become class attributes
                # Initialize in __init__
                transformed.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Functions become methods - transform them
                transformed.append(self._transform_to_method(node, method_names))
            else:
                # Other statements (keep as-is for now)
                transformed.append(node)

        return transformed

    def _transform_to_method(self, node, known_methods: Set[str] = None):
        """Transform a function into a method (add self, handle globals)."""
        # 1. Add self argument
        node.args.args.insert(0, ast.arg(arg='self'))
        
        # 2. Find global declarations and include known methods
        global_vars = set()
        if known_methods:
            global_vars.update(known_methods)
            
        new_body = []
        for stmt in node.body:
            if isinstance(stmt, ast.Global):
                global_vars.update(stmt.names)
            else:
                new_body.append(stmt)
        
        node.body = new_body
        
        # 3. Transform variable access
        if global_vars:
            class GlobalToSelf(ast.NodeTransformer):
                def visit_Name(self, n):
                    if n.id in global_vars:
                         return ast.Attribute(
                            value=ast.Name(id='self', ctx=ast.Load()),
                            attr=n.id,
                            ctx=n.ctx
                        )
                    return n
            
            # Apply transformation
            transformer = GlobalToSelf()
            for i, stmt in enumerate(node.body):
                node.body[i] = transformer.visit(stmt)
            
            # Fix locations
            for stmt in node.body:
                ast.fix_missing_locations(stmt)
                
        return node

    def _generate_render_method(self) -> ast.AsyncFunctionDef:
        """Generate render method."""
        return ast.AsyncFunctionDef(
            name='render',
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg='self')],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=[
                ast.Return(value=ast.Call(
                    func=ast.Name(id='Response', ctx=ast.Load()),
                    args=[
                        ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id='self', ctx=ast.Load()),
                                attr='_render_template',
                                ctx=ast.Load()
                            ),
                            args=[],
                            keywords=[]
                        )
                    ],
                    keywords=[
                        ast.keyword(arg='media_type', value=ast.Constant(value='text/html'))
                    ]
                ))
            ],
            decorator_list=[],
            returns=None
        )

    def _generate_render_template_method(self, parsed: ParsedPyHTML) -> Tuple[ast.FunctionDef, List[ast.AsyncFunctionDef]]:
        """Generate _render_template method and binding handlers."""
        # Generate code string from template
        code_str = self.template_codegen.generate_render_code(parsed.template)
        
        # Build SPA metadata injection
        path_directive = parsed.get_directive_by_type(PathDirective)
        no_spa = parsed.get_directive_by_type(NoSpaDirective) is not None
        is_multi_path = path_directive and not path_directive.is_simple_string
        spa_enabled = is_multi_path and not no_spa
        
        if spa_enabled and path_directive:
            sibling_paths = list(path_directive.routes.values())
            # Inject sibling paths as JSON for client-side link detection
            spa_meta = f'''
    # Inject SPA navigation metadata
    import json
    parts.append('<script id="_pyhtml_spa_meta" type="application/json">')
    parts.append(json.dumps({{"sibling_paths": {repr(sibling_paths)}}}))
    parts.append('</script>')
'''
        else:
            spa_meta = ""
        
        # Inject script tag for client library
        injection = f"""{spa_meta}
    # Inject client library script
    parts.append('<script src=\"/_pyhtml/static/pyhtml.min.js\"></script>')
"""
        # Find where to inject - before closing </body> or at end
        if "return" in code_str:
            code_str = code_str.replace("    return", injection + "    return")

        # Parse the generated code
        render_ast = ast.parse(code_str)
        render_func = render_ast.body[0] if isinstance(render_ast, ast.Module) and render_ast.body else None
        
        if not render_func:
             render_func = ast.FunctionDef(
                name='_render_template',
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg='self')],
                    vararg=None,
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[]
                ),
                body=[ast.Return(value=ast.Constant(value=''))],
                decorator_list=[],
                returns=None
            )

        # Generate binding methods
        binding_funcs = []
        for binding in self.template_codegen.generated_bindings:
            # async def _handle_bind_X(self, event_data):
            #     # self.var = event_data['value'] (or checked)
            #     val = event_data.get('value') # or checked
            #     if val is not None:
            #          # Cast? for now assume string or appropriate type
            #          self.var = val
            
            target = binding.variable_name # This is the raw string "var" or "self.var"
            # We need to construct assignment: target = value
            # Since target might be complex "user.name", we rely on ast parsing
            
            val_key = 'checked' if binding.event_type == 'change' and 'checked' in code_str else 'value'
            # Wait, 'checked' is for checkboxes. 
            # Logic in template.py: input[type=checkbox] -> type=change, stores 'checked' expr.
            # But the event data from client sends both value and checked?
            # Client code:
            # input: type=input, value=...
            # change: type=change, value=..., checked=...
            
            # If it's a checkbox, we want 'checked'. If text, 'value'.
            # BindingDef has event_type.
            if binding.event_type == 'change': # Checkbox/Radio implied
                val_key = 'checked'
            else:
                val_key = 'value'
            
            func_code = f"""
async def {binding.handler_name}(self, event_data):
    val = event_data.get('{val_key}')
    if val is not None:
        self.{target} = val
"""
            # Use `val` directly? Type casting?
            # For now raw.
            # Issue: `self.{target}` -> if target is `name`, then `self.name`.
            # If target is `self.name`, then `self.self.name`.
            # We need to normalize target.
            
            # In template.py: `variable=attr_value`. attr_value is raw "count".
            # transform_expr converts it to `self.count` only for rendering context.
            # Here we are in method context.
            
            # If user wrote `$bind="count"`. target="count". Code: `self.count = val`.
            # If user wrote `$bind="user.name"`. target="user.name". Code: `self.user.name = val`.
            # Correct.
            
            try:
                func_ast = ast.parse(func_code)
                if isinstance(func_ast, ast.Module) and func_ast.body:
                    binding_funcs.append(func_ast.body[0])
            except SyntaxError as e:
                print(f"Error generating binding handler for {binding.variable_name}: {e}")

        return render_func, binding_funcs

    def _generate_handle_event_method(self) -> ast.AsyncFunctionDef:
        """Generate handle_event method."""
        # Use a template string and parse it, much cleaner than manual AST construction
        code = """
async def handle_event(self, event_name: str, event_data: dict):
    import inspect
    
    # Retrieve handler
    handler = getattr(self, event_name, None)
    if not handler:
        raise ValueError(f"Handler {event_name} not found")

    # Call handler
    if event_name.startswith('_handle_bind_'):
        # Binding handlers expect raw event_data
        if asyncio.iscoroutinefunction(handler):
            await handler(event_data)
        else:
            handler(event_data)
    else:
        # Regular handlers: intelligent argument mapping
        args = event_data.get('args', {})
        
        # Normalize args keys (arg-0 -> arg0) because dataset keys preserve hyphens before digits
        normalized_args = {}
        for k, v in args.items():
            if k.startswith('arg'):
                normalized_args[k.replace('-', '')] = v
            else:
                normalized_args[k] = v
                
        call_kwargs = {k: v for k, v in event_data.items() if k != 'args'}
        call_kwargs.update(normalized_args)
        
        # Check signature to see what arguments the handler accepts
        sig = inspect.signature(handler)
        bound_kwargs = {}
        
        has_var_kw = False
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                has_var_kw = True
                break
        
        if has_var_kw:
            # If accepts **kwargs, pass everything
            bound_kwargs = call_kwargs
        else:
            # Only pass arguments that match parameters
            for name in sig.parameters:
                if name in call_kwargs:
                    bound_kwargs[name] = call_kwargs[name]
        
        if asyncio.iscoroutinefunction(handler):
            await handler(**bound_kwargs)
        else:
            handler(**bound_kwargs)
            
    # Re-render
    return await self.render()
"""
        module = ast.parse(code)
        return module.body[0]
