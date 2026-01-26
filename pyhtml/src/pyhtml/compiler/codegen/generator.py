"""Main code generator orchestrator."""
import ast
from typing import Dict, List, Type, Tuple, Set, Optional

from pyhtml.compiler.ast_nodes import (
    Directive, ParsedPyHTML, PathDirective, NoSpaDirective, SpecialAttribute, 
    EventAttribute, LayoutDirective, FormValidationSchema, FieldValidationRules, ModelAttribute
)
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
        self.file_path = parsed.file_path
        module_body = []

        # Imports
        module_body.extend(self._generate_imports())
        
        # Add asyncio import for handle_event
        module_body.append(
            ast.Import(names=[ast.alias(name='asyncio', asname=None)])
        )

        # Layout logic
        layout_directive = parsed.get_directive_by_type(LayoutDirective)
        base_class_name = 'BasePage'
        
        if layout_directive:
            # Import load_layout
            module_body.append(
                ast.ImportFrom(
                    module='pyhtml.runtime.loader',
                    names=[ast.alias(name='load_layout', asname=None)],
                    level=0
                )
            )
            # Load layout class
            # _LayoutBase = load_layout("path", __file_path__)
            module_body.append(
                ast.Assign(
                    targets=[ast.Name(id='_LayoutBase', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='load_layout', ctx=ast.Load()),
                        args=[
                            ast.Constant(value=layout_directive.layout_path),
                            ast.Constant(value=parsed.file_path)  # Pass page file path for relative resolution
                        ],
                        keywords=[]
                    )
                )
            )
            base_class_name = '_LayoutBase'


        # Extract user imports from Python section
        if parsed.python_ast:
            module_body.extend(self._extract_user_imports(parsed.python_ast))
            # Extract user classes to module level (Pydantic models, etc.)
            module_body.extend(self._extract_user_classes(parsed.python_ast))

        # Extract method names early for binding logic
        known_methods, known_vars, async_methods = self._collect_global_names(parsed.python_ast)
        known_imports = self._extract_import_names(parsed.python_ast)
        all_globals = known_methods.union(known_vars).union(known_imports)
        
        # Inline handlers (with method names)
        # Note: Handlers only need to know about globals to avoid "self." prefixing if needed, 
        # but _process_handlers mostly cares about wrapping logic.
        # Actually _process_handlers calls _transform_inline_code which uses known_methods.
        # Ideally it should know about all globals too.
        handlers = self._process_handlers(parsed, all_globals, async_methods)
        
        # Page class
        page_class = self._generate_page_class(parsed, handlers, known_methods, known_vars, known_imports, async_methods)
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
            # Form validation imports
            ast.ImportFrom(
                module='pyhtml.runtime.validation',
                names=[
                    ast.alias(name='form_validator', asname=None),
                    ast.alias(name='FieldRules', asname=None),
                    ast.alias(name='FormValidationSchema', asname=None)
                ],
                level=0
            ),
            ast.ImportFrom(
                module='pyhtml.runtime.pydantic_integration',
                names=[ast.alias(name='validate_with_model', asname=None)],
                level=0
            ),
        ]

    def _extract_user_imports(self, python_ast: ast.Module) -> List[ast.stmt]:
        """Extract import statements from user Python code."""
        imports = []
        for node in python_ast.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
        return imports

    def _extract_user_classes(self, python_ast: ast.Module) -> List[ast.stmt]:
        """Extract class definitions from user Python code."""
        classes = []
        for node in python_ast.body:
            if isinstance(node, ast.ClassDef):
                classes.append(node)
        return classes

    def _extract_import_names(self, python_ast: Optional[ast.Module]) -> Set[str]:
        """Extract names defined by imports."""
        names = set()
        # Add default imports
        names.add('json') 
        names.add('form_validator')
        names.add('FieldRules')
        
        if python_ast:
            for node in python_ast.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        names.add(alias.asname or alias.name)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        names.add(alias.asname or alias.name)
        return names

    def _generate_page_class(self, parsed: ParsedPyHTML, handlers: List[ast.AsyncFunctionDef], known_methods: Set[str], known_vars: Set[str], known_imports: Set[str], async_methods: Set[str]) -> ast.ClassDef:
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
        
        # Inject __no_spa__ flag if !no_spa was detected
        if parsed.get_directive_by_type(NoSpaDirective):
             class_body.append(ast.Assign(
                 targets=[ast.Name(id='__no_spa__', ctx=ast.Store())],
                 value=ast.Constant(value=True)
             ))

        # Generate __init__ method
        class_body.append(self._generate_init_method(parsed))

        # Transform user Python code to class methods
        all_globals = known_methods.union(known_vars)
        if parsed.python_ast:
            class_body.extend(self._transform_user_code(parsed.python_ast, all_globals))

        # Generate form validation schemas and wrappers
        # MUST happen before render generation as it updates EventAttributes to point to wrappers
        form_validation_methods = self._generate_form_validation_methods(parsed, all_globals)
        class_body.extend(form_validation_methods)        
        # Generate _render_template method AND binding methods
        # Pass ALL globals to avoid auto-calling variables and prefixing imports
        all_globals = known_methods.union(known_vars).union(known_imports)
        
        render_func, binding_funcs = self._generate_render_template_method(parsed, known_methods, all_globals, async_methods)
        if render_func:
            class_body.append(render_func)
        class_body.extend(binding_funcs)
        
        # Inject __has_uploads__ flag if file inputs were detected
        if self.template_codegen.has_file_inputs:
             class_body.append(ast.Assign(
                 targets=[ast.Name(id='__has_uploads__', ctx=ast.Store())],
                 value=ast.Constant(value=True)
             ))



        # Determine base class
        base_id = 'BasePage'
        layout_id_hash = None
        if parsed.file_path:
            import hashlib
            layout_id_hash = hashlib.md5(str(parsed.file_path).encode()).hexdigest()
            
            # Add LAYOUT_ID class attribute
            class_body.append(ast.Assign(
                 targets=[ast.Name(id='LAYOUT_ID', ctx=ast.Store())],
                 value=ast.Constant(value=layout_id_hash)
            ))
            
        if parsed.get_directive_by_type(LayoutDirective):
            base_id = '_LayoutBase'

        # Lifecycle hooks calculation
        init_hooks = ['on_before_load', 'on_load']
        # If we found @mount decorated methods
        if hasattr(self, '_collected_mount_hooks') and self._collected_mount_hooks:
            init_hooks.extend(self._collected_mount_hooks)
        
        # If we have top-level init code
        if hasattr(self, '_has_top_level_init') and self._has_top_level_init:
            init_hooks.insert(0, '__top_level_init__')

        # Add INIT_HOOKS class attribute override if we have extras
        # We can't easily access BasePage.INIT_HOOKS here without importing, 
        # relying on implicit knowledge that we are extending the list.
        # But to be safe and cleaner, we should probably output code that does:
        # INIT_HOOKS = BasePage.INIT_HOOKS + [...]
        # But we don't know if base is BasePage or _LayoutBase.
        # So we can generate:
        # INIT_HOOKS = list(BaseClass.INIT_HOOKS) + [...]
        # Or just re-declare the standard ones + extras. 
        # Page.py defines: INIT_HOOKS = ['on_before_load', 'on_load']
        # Let's enforce that sequence.
        
        # Ensure 'on_before_load' and 'on_load' are present
        final_init_hooks = []
        
        # Prepend generated top-level init
        if hasattr(self, '_has_top_level_init') and self._has_top_level_init:
             final_init_hooks.append('__top_level_init__')
             
        # Standard hooks - REMOVED per user request
        # final_init_hooks.append('on_before_load')
        # final_init_hooks.append('on_load')
        
        # Add mount hooks
        if hasattr(self, '_collected_mount_hooks') and self._collected_mount_hooks:
            final_init_hooks.extend(self._collected_mount_hooks)
            
        class_body.append(ast.Assign(
             targets=[ast.Name(id='INIT_HOOKS', ctx=ast.Store())],
             value=ast.List(
                 elts=[ast.Constant(value=h) for h in final_init_hooks],
                 ctx=ast.Load()
             )
        ))

        cls_def = ast.ClassDef(
            name=self._get_class_name(parsed),
            bases=[ast.Name(id=base_id, ctx=ast.Load())],
            keywords=[],
            body=class_body,
            decorator_list=[]
        )
        cls_def.lineno = 1
        cls_def.col_offset = 0
        return cls_def

    def _collect_global_names(self, python_ast: Optional[ast.Module]) -> Tuple[Set[str], Set[str], Set[str]]:
        """Collect defined function names and variables, and identify async functions.
           Returns: (method_names, variable_names, async_method_names)
        """
        methods = set()
        variables = {'path', 'params', 'query', 'url', 'request', 'error_code', 'error_detail', 'error_trace'}
        async_methods = set()
        
        if python_ast:
            for node in python_ast.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(node.name)
                    if isinstance(node, ast.AsyncFunctionDef):
                        async_methods.add(node.name)
                elif isinstance(node, ast.Assign):
                     for target in node.targets:
                         for child in ast.walk(target):
                             if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                                 variables.add(child.id)
                elif isinstance(node, ast.AnnAssign):
                     if isinstance(node.target, ast.Name):
                         variables.add(node.target.id)
        
        # Add implicit params from filename if available
        if hasattr(self, 'file_path') and self.file_path:
            import re
            from pathlib import Path
            path_obj = Path(self.file_path)
            # Check current file name and parent directories for [param] syntax
            for part in path_obj.parts:
                match = re.match(r'^\[(.*?)\]$', part.replace('.pyhtml', ''))
                if match:
                    variables.add(match.group(1))
        
        return methods, variables, async_methods

    def _process_handlers(self, parsed: ParsedPyHTML, known_methods: Set[str], async_methods: Set[str]) -> List[ast.AsyncFunctionDef]:
        """Extract inline handlers and wrap handlers for bindings."""
        handlers = []
        handler_count = 0
        from pyhtml.compiler.ast_nodes import EventAttribute, BindAttribute

        def visit_nodes(nodes):
            nonlocal handler_count
            for node in nodes:
                # Check for busy binding on this node
                busy_var = None
                for attr in node.special_attributes:
                    if isinstance(attr, BindAttribute) and attr.binding_type == 'busy':
                        busy_var = attr.variable
                        break
                
                # Check for events
                for attr in node.special_attributes:
                    if isinstance(attr, EventAttribute):
                        is_identifier = attr.handler_name.isidentifier()
                        needs_wrapper = (not is_identifier) or (busy_var is not None)
                        
                        if needs_wrapper:
                            # Create distinct handler methods
                            method_name = f'_handler_{handler_count}'
                            handler_count += 1
                            
                            try:
                                # Transform body logic
                                if is_identifier and busy_var:
                                    # Just a call to existing method, but needs wrapping for busy state
                                    # Transform loop will handle "method" -> "self.method"
                                    # But we need to make it a call "self.method(**bound_kwargs)"? 
                                    # Actually users write @click="method". 
                                    # If we wrap it, we generate:
                                    # async def _handler_X(self, arg0, ...):
                                    #     await self.method(arg0...)
                                    # BUT, handling arguments for a raw identifier wrapper is tricky because 
                                    # we don't know what args the original method expects if we just forward everything?
                                    # Actually, if the user wrote @click="method", and we act as proxy,
                                    # we should probably just treat "method" as the code to execute?
                                    # "method" as a statement evaluates to the function object, it doesn't CALL it.
                                    # Wait, existing `handle_event` calls the function.
                                    # If we generate a wrapper, the wrapper becomes the handler.
                                    # The wrapper body must CALL the original function.
                                    # So if @click="method", code is "method()".
                                    # If @click="method(arg)", code is "method(arg)".
                                    
                                    if is_identifier:
                                         # Logic change: simpler to explicitly call it with captured event data?
                                         # The wrapper receives (self, event_data) if we change the signature?
                                         # NO, existing logic extracts args from implicit calls.
                                         # If we have @click="method" and we wrap it, we don't easily know arguments.
                                         # COMPROMISE: If busy binding is used, we only support explicit calls or 0-arg calls easily
                                         # unless we change the wrapper signature to accept `**kwargs` and forward them.
                                         
                                         # Let's try treating it as an explicit call "method()" for now?
                                         # Or better: "await self.method()" and "self.method()"
                                         # But what if it takes args?
                                         # If the user uses @click="method" with busy binding, they probably expect args to potentially work.
                                         # However, getting that right is hard.
                                         # Let's assume for now `method()` (no args) or force user to use `@click="method()"` if they want busy binding?
                                         # actually `handle_event` passes args. 
                                         # Let's stick to: if it's an identifier, code = f"{attr.handler_name}()"
                                         # This risks missing args but is safe for parameterless methods.
                                         code_to_transform = f"{attr.handler_name}()"
                                else:
                                    code_to_transform = attr.handler_name

                                body, args = self._transform_inline_code(code_to_transform, known_methods, async_methods)
                                
                                # If busy binding, wrap body in try/finally
                                if busy_var:
                                    # self.busy_var = True
                                    set_busy = ast.Assign(
                                        targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=busy_var, ctx=ast.Store())],
                                        value=ast.Constant(value=True)
                                    )
                                    
                                    # await self._on_update()
                                    update_call = ast.Expr(value=ast.Await(value=ast.Call(
                                        func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='_on_update', ctx=ast.Load()),
                                        args=[], keywords=[]
                                    )))
                                    
                                    # Check if _on_update exists before calling? Runtime handles it, but safer to check?
                                    # "if self._on_update: await self._on_update()"
                                    check_update = ast.If(
                                        test=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='_on_update', ctx=ast.Load()),
                                        body=[update_call],
                                        orelse=[]
                                    )
                                    
                                    # finally: self.busy_var = False
                                    unset_busy = ast.Assign(
                                        targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=busy_var, ctx=ast.Store())],
                                        value=ast.Constant(value=False)
                                    )
                                    
                                    body = [
                                        set_busy,
                                        check_update,
                                        ast.Try(
                                            body=body,
                                            handlers=[],
                                            orelse=[],
                                            finalbody=[unset_busy]
                                        )
                                    ]

                                # Store extracted args
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
                                print(f"Error compiling handler '{attr.handler_name}': {e}")
                
                visit_nodes(node.children)

        visit_nodes(parsed.template)
        return handlers

    def _transform_inline_code(self, code: str, known_methods: Set[str] = None, async_methods: Set[str] = None) -> Tuple[List[ast.stmt], List[str]]:
        """Transform inline code: lift arguments and prefix globals with self."""
        import builtins
        
        # Map $event to event for Alpine compatibility
        code = code.replace('$event', 'event')
        
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
        
        if async_methods:
            class AsyncCallTransformer(ast.NodeTransformer):
                def visit_Call(self, node):
                    # Check if call to self.async_method
                    # The func is now (after ArgumentLifter/Name visit) self.method_name
                    if isinstance(node.func, ast.Attribute) and \
                       isinstance(node.func.value, ast.Name) and \
                       node.func.value.id == 'self' and \
                       node.func.attr in async_methods:
                        return ast.Await(value=node)
                    return self.generic_visit(node)
            
            AsyncCallTransformer().visit(new_tree)

        ast.fix_missing_locations(new_tree)
        
        return new_tree.body, extracted_args
    
    def _generate_form_validation_methods(self, parsed: ParsedPyHTML, known_globals: Set[str]) -> List[ast.stmt]:
        """Generate validation schema and wrapper methods for forms with @submit."""
        methods = []
        form_count = 0
        
        def visit_nodes(nodes):
            nonlocal form_count
            for node in nodes:
                # Check for form with @submit that has validation schema
                if node.tag and node.tag.lower() == 'form':
                    for attr in node.special_attributes:
                        if isinstance(attr, EventAttribute) and attr.event_type == 'submit':
                            if attr.validation_schema and attr.validation_schema.fields:
                                form_id = form_count
                                form_count += 1
                                
                                # Generate validation schema as class attribute
                                schema_name = f'_form_schema_{form_id}'
                                original_handler = attr.handler_name
                                
                                # Build dict literal for schema fields
                                schema_methods = self._generate_form_schema_literal(
                                    attr.validation_schema, schema_name, known_globals
                                )
                                methods.extend(schema_methods)
                                
                                # Generate wrapper handler
                                wrapper = self._generate_form_wrapper(
                                    form_id, original_handler, schema_name, 
                                    attr.validation_schema, known_globals
                                )
                                methods.append(wrapper)
                                
                                # Update handler name to point to wrapper
                                attr.handler_name = f'_form_submit_{form_id}'
                
                # Recurse
                visit_nodes(node.children)
        
        visit_nodes(parsed.template)
        return methods
    
    def _generate_form_schema_literal(self, schema: FormValidationSchema, schema_name: str, known_globals: Set[str]) -> List[ast.stmt]:
        """Generate validation schema as a class attribute."""
        field_items = []
        for field_name, rules in schema.fields.items():
            keywords = []
            
            if rules.required:
                keywords.append(ast.keyword(arg='required', value=ast.Constant(value=True)))
            if rules.required_expr:
                expr_ast = self.template_codegen._transform_expr(rules.required_expr, set(), known_globals)
                expr_str = ast.unparse(expr_ast)
                keywords.append(ast.keyword(arg='required_expr', value=ast.Constant(value=expr_str)))
            if rules.pattern:
                keywords.append(ast.keyword(arg='pattern', value=ast.Constant(value=rules.pattern)))
            if rules.minlength is not None:
                keywords.append(ast.keyword(arg='minlength', value=ast.Constant(value=rules.minlength)))
            if rules.maxlength is not None:
                keywords.append(ast.keyword(arg='maxlength', value=ast.Constant(value=rules.maxlength)))
            if rules.min_value:
                keywords.append(ast.keyword(arg='min_value', value=ast.Constant(value=rules.min_value)))
            if rules.min_expr:
                expr_ast = self.template_codegen._transform_expr(rules.min_expr, set(), known_globals)
                expr_str = ast.unparse(expr_ast)
                keywords.append(ast.keyword(arg='min_expr', value=ast.Constant(value=expr_str)))
            if rules.max_value:
                keywords.append(ast.keyword(arg='max_value', value=ast.Constant(value=rules.max_value)))
            if rules.max_expr:
                expr_ast = self.template_codegen._transform_expr(rules.max_expr, set(), known_globals)
                expr_str = ast.unparse(expr_ast)
                keywords.append(ast.keyword(arg='max_expr', value=ast.Constant(value=expr_str)))
            if rules.step:
                keywords.append(ast.keyword(arg='step', value=ast.Constant(value=rules.step)))
            if rules.input_type != 'text':
                keywords.append(ast.keyword(arg='input_type', value=ast.Constant(value=rules.input_type)))
            if rules.title:
                keywords.append(ast.keyword(arg='title', value=ast.Constant(value=rules.title)))
            if rules.max_size is not None:
                keywords.append(ast.keyword(arg='max_size', value=ast.Constant(value=rules.max_size)))
            if rules.allowed_types:
                keywords.append(ast.keyword(
                    arg='allowed_types', 
                    value=ast.List(
                        elts=[ast.Constant(value=t) for t in rules.allowed_types],
                        ctx=ast.Load()
                    )
                ))
            
            field_rules_call = ast.Call(
                func=ast.Name(id='FieldRules', ctx=ast.Load()),
                args=[],
                keywords=keywords
            )
            
            field_items.append((ast.Constant(value=field_name), field_rules_call))
        
        schema_dict = ast.Dict(
            keys=[k for k, v in field_items],
            values=[v for k, v in field_items]
        )
        
        schema_call = ast.Call(
            func=ast.Name(id='FormValidationSchema', ctx=ast.Load()),
            args=[],
            keywords=[
                ast.keyword(arg='fields', value=schema_dict)
            ]
        )
        
        if schema.model_name:
             schema_call.keywords.append(ast.keyword(
                 arg='model_name', 
                 value=ast.Constant(value=schema.model_name)
             ))
        
        return [
            ast.Assign(
                targets=[ast.Name(id=schema_name, ctx=ast.Store())],
                value=schema_call
            )
        ]
    
    def _generate_form_wrapper(
        self, 
        form_id: int, 
        original_handler: str, 
        schema_name: str,
        schema: FormValidationSchema,
        known_globals: Set[str]
    ) -> ast.AsyncFunctionDef:
        """Generate wrapper handler that validates then calls original handler."""
        wrapper_name = f'_form_submit_{form_id}'
        
        # Generate:
        # async def _form_submit_0(self, **kwargs):
        #     form_data = kwargs.get('formData', {})
        #     
        #     # Build state getter for conditional validation
        #     def get_state(expr):
        #         return eval(expr, {'self': self})
        #     
        #     # Validate
        #     self.errors = form_validator.validate_form(form_data, self._form_schema_0, get_state)
        #     if self.errors:
        #         return
        #     
        #     # Call original handler
        #     await self.original_handler(form_data)
        
        body = []
        
        # form_data = kwargs.get('formData', {})
        body.append(ast.Assign(
            targets=[ast.Name(id='form_data', ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='kwargs', ctx=ast.Load()),
                    attr='get',
                    ctx=ast.Load()
                ),
                args=[ast.Constant(value='formData'), ast.Dict(keys=[], values=[])],
                keywords=[]
            )
        ))
        
        # Define state getter for conditional validation
        # def get_state(expr):
        #     return eval(expr, {'self': self})
        state_getter = ast.FunctionDef(
            name='get_state',
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg='expr')],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=[
                ast.Return(value=ast.Call(
                    func=ast.Name(id='eval', ctx=ast.Load()),
                    args=[
                        ast.Name(id='expr', ctx=ast.Load()),
                        ast.Call(
                            func=ast.Attribute(
                                value=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='__dict__', ctx=ast.Load()),
                                attr='copy',
                                ctx=ast.Load()
                            ),
                            args=[],
                            keywords=[]
                        ),
                        # Make 'self' and global imports available
                        ast.Dict(
                            keys=[ast.Constant(value='self')] + [ast.Constant(value=name) for name in known_globals],
                            values=[ast.Name(id='self', ctx=ast.Load())] + [ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=name, ctx=ast.Load()) for name in known_globals]
                        )
                    ],
                    keywords=[]
                ))
            ],
            decorator_list=[],
            returns=None
        )
        body.append(state_getter)
        
        # cleaned_data, self.errors = form_validator.validate_form(form_data, self._form_schema_X.fields, get_state)
        # Note: pass .fields from the schema object
        body.append(ast.Assign(
            targets=[ast.Tuple(
                elts=[
                    ast.Name(id='cleaned_data', ctx=ast.Store()),
                    ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='errors',
                        ctx=ast.Store()
                    )
                ],
                ctx=ast.Store()
            )],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='form_validator', ctx=ast.Load()),
                    attr='validate_form',
                    ctx=ast.Load()
                ),
                args=[
                    ast.Name(id='form_data', ctx=ast.Load()),
                    ast.Attribute(
                        value=ast.Attribute(
                             value=ast.Name(id='self', ctx=ast.Load()),
                             attr=schema_name,
                             ctx=ast.Load()
                        ),
                        attr='fields',
                        ctx=ast.Load()
                    ),
                    ast.Name(id='get_state', ctx=ast.Load())
                ],
                keywords=[]
            )
        ))
        
        # If Pydantic model is used:
        # if not self.errors and self._form_schema_X.model_name:
        #    model_instance, pydantic_errors = validate_with_model(cleaned_data, globals()[self._form_schema_X.model_name])
        #    if pydantic_errors:
        #        self.errors.update(pydantic_errors)
        #    else:
        #        cleaned_data = model_instance # Replace dict with model instance
        
        if schema.model_name:
            pydantic_block = []
            
            # model_instance, pydantic_errors = validate_with_model(cleaned_data, ModelClass)
            
            # PARSE NESTED DATA FIRST
            # nested_data = form_validator.parse_nested_data(cleaned_data)
            pydantic_block.append(ast.Assign(
                 targets=[ast.Name(id='nested_data', ctx=ast.Store())],
                 value=ast.Call(
                     func=ast.Attribute(
                         value=ast.Name(id='form_validator', ctx=ast.Load()),
                         attr='parse_nested_data',
                         ctx=ast.Load()
                     ),
                     args=[ast.Name(id='cleaned_data', ctx=ast.Load())],
                     keywords=[]
                 )
            ))

            validate_call = ast.Call(
                func=ast.Name(id='validate_with_model', ctx=ast.Load()),
                args=[
                    ast.Name(id='nested_data', ctx=ast.Load()),
                    ast.Name(id=schema.model_name, ctx=ast.Load()) 
                ],
                keywords=[]
            )
            
            pydantic_block.append(ast.Assign(
                 targets=[ast.Tuple(
                     elts=[
                         ast.Name(id='model_instance', ctx=ast.Store()),
                         ast.Name(id='pydantic_errors', ctx=ast.Store())
                     ],
                     ctx=ast.Store()
                 )],
                 value=validate_call
            ))
            
            # if pydantic_errors: self.errors.update(pydantic_errors)
            # else: cleaned_data = model_instance
            pydantic_block.append(ast.If(
                test=ast.Name(id='pydantic_errors', ctx=ast.Load()),
                body=[
                    ast.Expr(value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='errors', ctx=ast.Load()),
                            attr='update',
                            ctx=ast.Load()
                        ),
                        args=[ast.Name(id='pydantic_errors', ctx=ast.Load())],
                        keywords=[]
                    ))
                ],
                orelse=[
                    ast.Assign(
                        targets=[ast.Name(id='cleaned_data', ctx=ast.Store())],
                        value=ast.Name(id='model_instance', ctx=ast.Load())
                    )
                ]
            ))
            
            # Wrap in check: if not self.errors:
            body.append(ast.If(
                test=ast.UnaryOp(
                    op=ast.Not(),
                    operand=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='errors', ctx=ast.Load())
                ),
                body=pydantic_block,
                orelse=[]
            ))
        
        # if self.errors: return
        body.append(ast.If(
            test=ast.Attribute(
                value=ast.Name(id='self', ctx=ast.Load()),
                attr='errors',
                ctx=ast.Load()
            ),
            body=[ast.Return(value=None)],
            orelse=[]
        ))
        
        # Call original handler - need to check if it's async
        handler_call = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id='self', ctx=ast.Load()),
                attr=original_handler,
                ctx=ast.Load()
            ),
            args=[ast.Name(id='cleaned_data', ctx=ast.Load())],
            keywords=[]
        )
        
        # Assume async for safety - await it
        body.append(ast.Expr(value=ast.Await(value=handler_call)))
        
        return ast.AsyncFunctionDef(
            name=wrapper_name,
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg='self')],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=ast.arg(arg='kwargs'),
                defaults=[]
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

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
                )),
                # Call _init_slots
                ast.Expr(value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='_init_slots',
                        ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[]
                ))
            ],
            decorator_list=[],
            returns=None
        )

    def _transform_user_code(self, python_ast: ast.Module, known_globals: Set[str] = None) -> List[ast.stmt]:
        """Transform user Python code to class methods/attributes."""
        transformed = []
        if known_globals is None:
            known_globals = set()
            
        # Collect hooks
        self._collected_mount_hooks = []
        self._has_top_level_init = False
        
        top_level_statements = []
        
        for node in python_ast.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Skip imports - already handled
                continue
            elif isinstance(node, ast.Assign):
                # Module-level assignments become class attributes
                # UNLESS they target 'self' (e.g. self.x = 1), which makes no sense at class level
                # and implies instance initialization.
                
                is_instance_assign = False
                for target in node.targets:
                    # Check if target is Attribute(value=Name(id='self'))
                    if isinstance(target, ast.Attribute) and \
                       isinstance(target.value, ast.Name) and \
                       target.value.id == 'self':
                        is_instance_assign = True
                        break
                        
                if is_instance_assign:
                    top_level_statements.append(node)
                else:
                    # BUT, if they rely on runtime values (like other vars), they should be in __init__
                    # For now, we assume static assignments. 
                    # If the value calls a function, it might be safer in __top_level_init__.
                    # Heuristic: Check if value is constant?
                    # "top level statements will be considered on_load... obviously not each RTT request"
                    # "execute on first load" -> init=True.
                    
                    # So executable statements (Calls, Loops, Ifs) definitely go to `__top_level_init__`.
                    # Simple assignments `x = 1`?
                    # If `x = 1`, it stays class attr (default user expectation for python scripts?).
                    transformed.append(node)
                     
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for decorators
                is_mount = False
                new_decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == 'mount':
                        is_mount = True
                        self._collected_mount_hooks.append(node.name)
                    elif isinstance(dec, ast.Name) and dec.id == 'unmount':
                        # Placeholder for future unmount
                        pass 
                    else:
                        new_decorators.append(dec)
                
                node.decorator_list = new_decorators
                
                # Functions become methods - transform them
                transformed.append(self._transform_to_method(node, known_globals))
            elif isinstance(node, ast.ClassDef):
                # Classes are moved to module level, skip here
                continue
            else:
                # Other statements (Expr, If, For, While, Try)
                # Move to top-level init
                top_level_statements.append(node)

        if top_level_statements:
            self._has_top_level_init = True
            transformed.append(self._generate_top_level_init(top_level_statements, known_globals))

        return transformed

    def _generate_top_level_init(self, statements: List[ast.stmt], known_globals: Set[str]) -> ast.AsyncFunctionDef:
        """Generate __top_level_init__ method from top-level statements."""
        
        # 1. Collect all variables assigned in this scope to promote them to instance attributes.
        # This ensures 'x = 1' inside match/if/for becomes 'self.x = 1'.
        local_assignments = set()
        
        class AssignmentCollector(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                # Do not recurse into nested functions
                pass
            def visit_AsyncFunctionDef(self, node):
                pass
            def visit_ClassDef(self, node):
                pass
            
            def visit_Name(self, node):
                # If name is being stored (assigned to), collect it
                if isinstance(node.ctx, ast.Store):
                    local_assignments.add(node.id)

        collector = AssignmentCollector()
        for stmt in statements:
            collector.visit(stmt)
            
        # Combine with explicit known globals
        # We start with a copy to avoid mutating the passed set if it's used elsewhere (though it seems local usually)
        combined_globals = set(known_globals)
        combined_globals.update(local_assignments)

        # Wrap statements in async method
        # Transform variables to self.X
        
        wrapper = ast.AsyncFunctionDef(
            name='__top_level_init__',
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg='self')],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=statements,
            decorator_list=[],
            returns=None
        )
        
        return self._transform_to_method(wrapper, combined_globals)

    def _transform_to_method(self, node, known_methods: Set[str] = None):
        """Transform a function into a method (add self, handle globals)."""
        # 1. Add self argument if not present
        if not (node.args.args and node.args.args[0].arg == 'self'):
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
                        ast.Await(value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id='self', ctx=ast.Load()),
                                attr='_render_template',
                                ctx=ast.Load()
                            ),
                            args=[],
                            keywords=[]
                        ))
                    ],
                    keywords=[
                        ast.keyword(arg='media_type', value=ast.Constant(value='text/html'))
                    ]
                ))
            ],
            decorator_list=[],
            returns=None
        )

    def _generate_render_template_method(self, parsed: ParsedPyHTML, known_methods: Set[str] = None, known_globals: Set[str] = None, async_methods: Set[str] = None) -> Tuple[Optional[ast.FunctionDef], List[ast.AsyncFunctionDef]]:
        """Generate _render_template method and binding/slot handlers."""
        # Check for layout
        layout_directive = parsed.get_directive_by_type(LayoutDirective)
        
        binding_funcs = []
        render_func = None
        
        if layout_directive:
            # === Layout Mode ===
            file_id = parsed.file_path or ""
            
            # Ensure layout_id is generated for intermediate layouts
            import hashlib
            layout_id = hashlib.md5(str(parsed.file_path).encode()).hexdigest() if parsed.file_path else None
            
            slot_funcs_methods, aux_funcs = self.template_codegen.generate_slot_methods(
                parsed.template, 
                file_id=file_id, 
                known_globals=known_globals,
                layout_id=layout_id
            )
            
            file_hash = hashlib.md5(file_id.encode()).hexdigest()[:8] if file_id else ""
            
            # Add slot methods directly (they are ASTs now)
            for slot_name, func_ast in slot_funcs_methods.items():
                binding_funcs.append(func_ast)
            
            # Add aux funcs
            binding_funcs.extend(aux_funcs)

            # Generate _init_slots
            
            # Resolve parent layout path
            from pathlib import Path
            parent_layout_path = layout_directive.layout_path
            if not Path(parent_layout_path).is_absolute():
                base_dir = Path(parsed.file_path).parent if parsed.file_path else Path.cwd()
                parent_layout_path = str((base_dir / parent_layout_path).resolve())
            else:
                parent_layout_path = str(Path(parent_layout_path).resolve())
            
            def make_parent_layout_id():
                import hashlib
                parent_hash = hashlib.md5(parent_layout_path.encode()).hexdigest()
                return ast.Constant(value=parent_hash)

            init_slots_body = []
            
            # Chain super
            super_check = ast.If(
                test=ast.Call(
                    func=ast.Name(id='hasattr', ctx=ast.Load()),
                    args=[
                        ast.Call(func=ast.Name(id='super', ctx=ast.Load()), args=[], keywords=[]),
                        ast.Constant(value='_init_slots')
                    ],
                    keywords=[]
                ),
                body=[ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Call(func=ast.Name(id='super', ctx=ast.Load()), args=[], keywords=[]), attr='_init_slots', ctx=ast.Load()), args=[], keywords=[]))],
                orelse=[]
            )
            init_slots_body.append(super_check)

            for slot_name in slot_funcs_methods.keys():
                safe_name = slot_name.replace('$', '_head_').replace('-', '_') if slot_name.startswith('$') else slot_name.replace('-', '_')
                func_name = f'_render_slot_fill_{safe_name}_{file_hash}' if file_hash else f'_render_slot_fill_{safe_name}'
                
                if slot_name == '$head':
                    reg_call = ast.Expr(value=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='register_head_slot', ctx=ast.Load()),
                        args=[make_parent_layout_id(), ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=func_name, ctx=ast.Load())],
                        keywords=[]
                    ))
                else:
                    reg_call = ast.Expr(value=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='register_slot', ctx=ast.Load()),
                        args=[make_parent_layout_id(), ast.Constant(value=slot_name), ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=func_name, ctx=ast.Load())],
                        keywords=[]
                    ))
                init_slots_body.append(reg_call)
                
            init_slots_func = ast.FunctionDef(
                name='_init_slots',
                args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self')], vararg=None, kwonlyargs=[], kw_defaults=[], defaults=[]),
                body=init_slots_body,
                decorator_list=[],
                returns=None
            )
            binding_funcs.append(init_slots_func)

        else:
            # === Standard Mode ===
            import hashlib
            layout_id = hashlib.md5(str(parsed.file_path).encode()).hexdigest() if parsed.file_path else None
            
            render_func, aux_funcs = self.template_codegen.generate_render_method(
                parsed.template, layout_id=layout_id,
                known_methods=known_methods, known_globals=known_globals, async_methods=async_methods
            )
            binding_funcs.extend(aux_funcs)

            # SPA injection
            path_directive = parsed.get_directive_by_type(PathDirective)
            no_spa = parsed.get_directive_by_type(NoSpaDirective) is not None
            is_multi_path = path_directive and not path_directive.is_simple_string
            spa_enabled = is_multi_path and not no_spa
            
            # Determine injection point (before final return)
            
            spa_check = ast.If(
                test=ast.BoolOp(op=ast.And(), values=[
                    ast.UnaryOp(op=ast.Not(), operand=ast.Call(func=ast.Name(id='getattr', ctx=ast.Load()), args=[ast.Name(id='self', ctx=ast.Load()), ast.Constant(value="__no_spa__"), ast.Constant(value=False)], keywords=[])),
                    ast.BoolOp(op=ast.Or(), values=[
                        ast.Call(func=ast.Name(id='getattr', ctx=ast.Load()), args=[ast.Name(id='self', ctx=ast.Load()), ast.Constant(value="__spa_enabled__"), ast.Constant(value=False)], keywords=[]),
                        ast.Call(func=ast.Name(id='getattr', ctx=ast.Load()), args=[ast.Attribute(value=ast.Attribute(value=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='request', ctx=ast.Load()), attr='app', ctx=ast.Load()), attr='state', ctx=ast.Load()), ast.Constant(value='enable_pjax'), ast.Constant(value=False)], keywords=[])
                    ])
                ]),
                body=[
                    # sibling_paths = ...
                    ast.Assign(targets=[ast.Name(id='sibling_paths', ctx=ast.Store())], value=ast.Call(func=ast.Name(id='getattr', ctx=ast.Load()), args=[ast.Name(id='self', ctx=ast.Load()), ast.Constant(value="__sibling_paths__"), ast.List(elts=[], ctx=ast.Load())], keywords=[])),
                    # pjax_enabled = ...
                    ast.Assign(targets=[ast.Name(id='pjax_enabled', ctx=ast.Store())], value=ast.Call(func=ast.Name(id='getattr', ctx=ast.Load()), args=[ast.Attribute(value=ast.Attribute(value=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='request', ctx=ast.Load()), attr='app', ctx=ast.Load()), attr='state', ctx=ast.Load()), ast.Constant(value='enable_pjax'), ast.Constant(value=False)], keywords=[])),
                    # parts.append(script tag)
                    ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()), args=[ast.Constant(value='<script id="_pyhtml_spa_meta" type="application/json">')], keywords=[])),
                    # parts.append(json.dumps(...))
                    ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()), 
                        args=[ast.Call(func=ast.Attribute(value=ast.Name(id='json', ctx=ast.Load()), attr='dumps', ctx=ast.Load()), 
                            args=[ast.Dict(keys=[ast.Constant(value='sibling_paths'), ast.Constant(value='enable_pjax')], values=[ast.Name(id='sibling_paths', ctx=ast.Load()), ast.Name(id='pjax_enabled', ctx=ast.Load())])], keywords=[])], 
                        keywords=[])),
                    ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()), args=[ast.Constant(value='</script>')], keywords=[])),
                    # parts.append(client lib) - dynamically select core vs dev bundle
                    # parts.append(f'<script src="{self.request.app.state.pyhtml._get_client_script_url()}"></script>')
                    ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id='parts', ctx=ast.Load()), attr='append', ctx=ast.Load()), 
                        args=[ast.JoinedStr(values=[
                            ast.Constant(value='<script src="'),
                            ast.FormattedValue(value=ast.Call(
                                func=ast.Attribute(
                                    value=ast.Attribute(
                                        value=ast.Attribute(value=ast.Attribute(value=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='request', ctx=ast.Load()), attr='app', ctx=ast.Load()), attr='state', ctx=ast.Load()),
                                        attr='pyhtml', ctx=ast.Load()
                                    ),
                                    attr='_get_client_script_url', ctx=ast.Load()
                                ),
                                args=[], keywords=[]
                            ), conversion=-1, format_spec=None),
                            ast.Constant(value='"></script>')
                        ])], 
                        keywords=[]))
                ],
                orelse=[]
            )
            
            # Insert before last statement
            if render_func.body and isinstance(render_func.body[-1], ast.Return):
                render_func.body.insert(-1, spa_check)
            else:
                render_func.body.append(spa_check)
            
            # Add no-op _init_slots
            binding_funcs.append(ast.FunctionDef(name='_init_slots', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self')], vararg=None, kwonlyargs=[], kw_defaults=[], defaults=[]), body=[ast.Pass()], decorator_list=[], returns=None))

        # Generate binding methods
        for binding in self.template_codegen.generated_bindings:
            target = binding.variable_name
            # Unparse check if necessary, but here we can rely on standard keys
            val_key = 'value'
            if binding.event_type == 'change': val_key = 'checked'
            elif binding.event_type == 'upload-progress': val_key = 'progress'
            
            handler_body = [
                ast.Assign(
                    targets=[ast.Name(id='val', ctx=ast.Store())],
                    value=ast.Call(func=ast.Attribute(value=ast.Name(id='event_data', ctx=ast.Load()), attr='get', ctx=ast.Load()), args=[ast.Constant(value=val_key)], keywords=[])
                ),
                ast.If(
                    test=ast.Compare(left=ast.Name(id='val', ctx=ast.Load()), ops=[ast.IsNot()], comparators=[ast.Constant(value=None)]),
                    body=[ast.Assign(
                        targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=target, ctx=ast.Store())],
                        value=ast.Name(id='val', ctx=ast.Load())
                    )],
                    orelse=[]
                )
            ]
            
            binding_funcs.append(ast.AsyncFunctionDef(
                name=binding.handler_name,
                args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self'), ast.arg(arg='event_data')], vararg=None, kwonlyargs=[], kw_defaults=[], defaults=[]),
                body=handler_body,
                decorator_list=[],
                returns=None
            ))

        return render_func, binding_funcs


