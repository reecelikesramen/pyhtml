"""Main code generator orchestrator."""
import ast
from typing import Dict, List, Type

from pyhtml.compiler.ast_nodes import Directive, ParsedPyHTML, PathDirective, SpecialAttribute, EventAttribute
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

        # Page class
        page_class = self._generate_page_class(parsed)
        module_body.append(page_class)

        return ast.Module(body=module_body, type_ignores=[])

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
        ]

    def _extract_user_imports(self, python_ast: ast.Module) -> List[ast.stmt]:
        """Extract import statements from user Python code."""
        imports = []
        for node in python_ast.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
        return imports

    def _generate_page_class(self, parsed: ParsedPyHTML) -> ast.ClassDef:
        """Generate page class definition."""
        class_body = []

        # Generate directive assignments
        for directive in parsed.directives:
            handler = self.directive_handlers.get(type(directive))
            if handler:
                class_body.extend(handler.generate(directive))

        # Generate __init__ method
        class_body.append(self._generate_init_method(parsed))

        # Transform user Python code to class methods
        if parsed.python_ast:
            class_body.extend(self._transform_user_code(parsed.python_ast))

        # Generate render method
        class_body.append(self._generate_render_method())

        # Extract inline handlers BEFORE render template (modifies EventAttribute.handler_name)
        inline_handlers = self._extract_inline_handlers(parsed)
        class_body.extend(inline_handlers)

        # Generate _render_template method (uses updated handler names)
        class_body.append(self._generate_render_template_method(parsed))

        # Generate handle_event method
        class_body.append(self._generate_handle_event_method())

        return ast.ClassDef(
            name=self._get_class_name(parsed),
            bases=[ast.Name(id='BasePage', ctx=ast.Load())],
            keywords=[],
            body=class_body,
            decorator_list=[]
        )

    def _extract_inline_handlers(self, parsed: ParsedPyHTML) -> List[ast.AsyncFunctionDef]:
        """Extract inline handlers to methods."""
        handlers = []
        handler_count = 0
        from pyhtml.compiler.ast_nodes import EventAttribute

        # Collect async method names
        async_methods = set()
        if parsed.python_ast:
             for node in parsed.python_ast.body:
                 if isinstance(node, ast.AsyncFunctionDef):
                     async_methods.add(node.name)

        # Traverse template for event attributes
        # This is simple recursive traversal
        def visit_nodes(nodes):
            nonlocal handler_count
            for node in nodes:
                for attr in node.special_attributes:
                    if isinstance(attr, EventAttribute):
                        # Check if valid identifier
                        if not attr.handler_name.isidentifier():
                            # It's inline code
                            # Use single underscore to verify name mangling doesn't happen
                            method_name = f'_handler_{handler_count}'
                            handler_count += 1
                            
                            # Transform code
                            try:
                                body = self._transform_inline_code(attr.handler_name, async_methods)
                                
                                # Create method
                                handlers.append(ast.AsyncFunctionDef(
                                    name=method_name,
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
                                ))
                                
                                # Update attribute to point to new method
                                attr.handler_name = method_name
                                
                            except Exception as e:
                                print(f"Error compiling inline handler '{attr.handler_name}': {e}")
                
                visit_nodes(node.children)

        visit_nodes(parsed.template)
        return handlers

    def _transform_inline_code(self, code: str, async_methods: set = None) -> List[ast.stmt]:
        """Transform inline code to method body (prefix vars with self)."""
        import builtins
        
        # Parse code
        tree = ast.parse(code)
        
        class SelfTransformer(ast.NodeTransformer):
            def visit_Name(self, node):
                # Don't transform if it's a builtin
                if node.id in dir(builtins):
                    return node
                
                # Check context
                if isinstance(node.ctx, (ast.Load, ast.Store, ast.Del)):
                    return ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=node.id,
                        ctx=node.ctx
                    )
                return node

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
                transformed.append(self._transform_to_method(node))
            else:
                # Other statements (keep as-is for now)
                transformed.append(node)

        return transformed

    def _transform_to_method(self, node):
        """Transform a function into a method (add self, handle globals)."""
        # 1. Add self argument
        node.args.args.insert(0, ast.arg(arg='self'))
        
        # 2. Find global declarations
        global_vars = set()
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

    def _generate_render_template_method(self, parsed: ParsedPyHTML) -> ast.FunctionDef:
        """Generate _render_template method."""
        # Generate code string from template
        code_str = self.template_codegen.generate_render_code(parsed.template)
        
        # Inject script tag for client library
        injection = """
    # Inject client library script
    parts.append('<script src="/_pyhtml/static/pyhtml.min.js"></script>')
"""
        # Find where to inject - before closing </body> or at end
        if "return" in code_str:
            # Simple string replacement for now
            # In a robust implementation, we'd add AST nodes
            code_str = code_str.replace("    return", injection + "    return")

        # Parse the generated code
        render_ast = ast.parse(code_str)
        
        # Extract the function definition
        if isinstance(render_ast, ast.Module) and render_ast.body:
            return render_ast.body[0]
        
        # Fallback
        return ast.FunctionDef(
            name='_render_template',
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg='self')],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=[
                ast.Return(value=ast.Constant(value=''))
            ],
            decorator_list=[],
            returns=None
        )

    def _generate_handle_event_method(self) -> ast.AsyncFunctionDef:
        """Generate handle_event method."""
        return ast.AsyncFunctionDef(
            name='handle_event',
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg='self'),
                    ast.arg(arg='event_name'),
                    ast.arg(arg='event_data')
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=[
                # handler = getattr(self, event_name, None)
                ast.Assign(
                    targets=[ast.Name(id='handler', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='getattr', ctx=ast.Load()),
                        args=[
                            ast.Name(id='self', ctx=ast.Load()),
                            ast.Name(id='event_name', ctx=ast.Load()),
                            ast.Constant(value=None)
                        ],
                        keywords=[]
                    )
                ),
                # if not handler: raise ValueError(...)
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Name(id='handler', ctx=ast.Load())
                    ),
                    body=[
                        ast.Raise(
                            exc=ast.Call(
                                func=ast.Name(id='ValueError', ctx=ast.Load()),
                                args=[
                                    ast.JoinedStr(
                                        values=[
                                            ast.Constant(value='Handler '),
                                            ast.FormattedValue(
                                                value=ast.Name(id='event_name', ctx=ast.Load()),
                                                conversion=-1,
                                                format_spec=None
                                            ),
                                            ast.Constant(value=' not found')
                                        ]
                                    )
                                ],
                                keywords=[]
                            ),
                            cause=None
                        )
                    ],
                    orelse=[]
                ),
                # Call handler (async-aware)
                ast.If(
                    test=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id='asyncio', ctx=ast.Load()),
                            attr='iscoroutinefunction',
                            ctx=ast.Load()
                        ),
                        args=[ast.Name(id='handler', ctx=ast.Load())],
                        keywords=[]
                    ),
                    body=[
                        ast.Expr(value=ast.Await(value=ast.Call(
                            func=ast.Name(id='handler', ctx=ast.Load()),
                            args=[],
                            keywords=[
                                ast.keyword(
                                    arg=None,
                                    value=ast.Call(
                                        func=ast.Attribute(
                                            value=ast.Name(id='event_data', ctx=ast.Load()),
                                            attr='get',
                                            ctx=ast.Load()
                                        ),
                                        args=[
                                            ast.Constant(value='args'),
                                            ast.Dict(keys=[], values=[])
                                        ],
                                        keywords=[]
                                    )
                                )
                            ]
                        )))
                    ],
                    orelse=[
                        ast.Expr(value=ast.Call(
                            func=ast.Name(id='handler', ctx=ast.Load()),
                            args=[],
                            keywords=[
                                ast.keyword(
                                    arg=None,
                                    value=ast.Call(
                                        func=ast.Attribute(
                                            value=ast.Name(id='event_data', ctx=ast.Load()),
                                            attr='get',
                                            ctx=ast.Load()
                                        ),
                                        args=[
                                            ast.Constant(value='args'),
                                            ast.Dict(keys=[], values=[])
                                        ],
                                        keywords=[]
                                    )
                                )
                            ]
                        ))
                    ]
                ),
                # Return render()
                ast.Return(value=ast.Await(value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='render',
                        ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[]
                )))
            ],
            decorator_list=[],
            returns=None
        )
