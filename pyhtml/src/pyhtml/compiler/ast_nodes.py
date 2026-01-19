"""AST node definitions for PyHTML compiler."""
import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


@dataclass
class ASTNode:
    """Base for all AST nodes."""
    line: int
    column: int


@dataclass
class Directive(ASTNode):
    """Base for directives."""
    name: str


@dataclass
class PathDirective(Directive):
    """!path { 'name': '/route/{param}' } or !path '/route'"""
    routes: Dict[str, str]  # {'name': '/route/{param}'}
    is_simple_string: bool = False

    def __str__(self) -> str:
        return f"PathDirective(routes={self.routes}, simple={self.is_simple_string})"


@dataclass
class NoSpaDirective(Directive):
    """!no_spa - disables client-side SPA navigation for this page."""

    def __str__(self) -> str:
        return "NoSpaDirective()"


@dataclass
class LayoutDirective(Directive):
    """!layout "path/to/layout.pyhtml" """
    layout_path: str

    def __str__(self) -> str:
        return f"LayoutDirective(path={self.layout_path})"


@dataclass
class SpecialAttribute(ASTNode):
    """Base for special attributes ($, @, :)."""
    name: str
    value: str


@dataclass
class KeyAttribute(SpecialAttribute):
    """$key="unique_id"."""
    expr: str

    def __str__(self) -> str:
        return f"KeyAttribute(expr={self.expr})"


@dataclass
class IfAttribute(SpecialAttribute):
    """$if="condition"."""
    condition: str
    
    def __str__(self) -> str:
        return f"IfAttribute(condition={self.condition})"


@dataclass
class ShowAttribute(SpecialAttribute):
    """$show="condition"."""
    condition: str
    
    def __str__(self) -> str:
        return f"ShowAttribute(condition={self.condition})"


@dataclass
class ForAttribute(SpecialAttribute):
    """$for="item in items"."""
    is_template_tag: bool # <template $for>
    loop_vars: str # "item" or "key, value"
    iterable: str # "items" or "items.items()"
    key: Optional[str] = None
    
    def __str__(self) -> str:
        return f"ForAttribute(vars={self.loop_vars}, in={self.iterable})"


@dataclass
class BindAttribute(SpecialAttribute):
    """$bind="variable"."""
    variable: str
    binding_type: Optional[str] = None
    
    def __str__(self) -> str:
        return f"BindAttribute(var={self.variable}, type={self.binding_type})"


@dataclass
class EventAttribute(SpecialAttribute):
    """@click="handler_name" or @click="handler(arg1)"."""
    event_type: str  # 'click', 'submit', etc.
    handler_name: str
    args: List[str] = field(default_factory=list)  # List of python expressions for arguments

    def __str__(self) -> str:
        return f"EventAttribute(event={self.event_type}, handler={self.handler_name}, args={self.args})"


@dataclass
class ReactiveAttribute(SpecialAttribute):
    """
    :attr="expression"
    Represents a reactive attribute where the value is a python expression.
    """
    expr: str

    def __str__(self) -> str:
        return f"ReactiveAttribute(name={self.name}, expr={self.expr})"


@dataclass
class InterpolationNode(ASTNode):
    """Represents {variable} in text."""
    expression: str  # Python expression to evaluate

    def __str__(self) -> str:
        return f"InterpolationNode(expr={self.expression})"


@dataclass
class TemplateNode(ASTNode):
    """HTML element or text node."""
    tag: Optional[str]  # None for text nodes
    attributes: Dict[str, str] = field(default_factory=dict)  # Regular HTML attributes
    special_attributes: List[SpecialAttribute] = field(default_factory=list)
    children: List['TemplateNode'] = field(default_factory=list)
    text_content: Optional[str] = None

    def __str__(self) -> str:
        if self.tag:
            return f"TemplateNode(tag={self.tag}, attrs={len(self.attributes)}, special={len(self.special_attributes)}, children={len(self.children)})"
        return f"TemplateNode(text={self.text_content[:30] if self.text_content else None})"


@dataclass
class ParsedPyHTML:
    """Top-level parsed document."""
    directives: List[Directive] = field(default_factory=list)
    template: List[TemplateNode] = field(default_factory=list)
    python_code: str = ""  # Raw Python section (below ---)
    python_ast: Optional[ast.Module] = None  # Parsed Python AST
    file_path: str = ""

    def get_directive_by_type(self, directive_type: type) -> Optional[Directive]:
        """Get first directive of specified type."""
        for directive in self.directives:
            if isinstance(directive, directive_type):
                return directive
        return None

    def get_directives_by_type(self, directive_type: type) -> List[Directive]:
        """Get all directives of specified type."""
        return [d for d in self.directives if isinstance(d, directive_type)]

    def __str__(self) -> str:
        return f"ParsedPyHTML(directives={len(self.directives)}, template_nodes={len(self.template)}, python_lines={len(self.python_code.splitlines())})"
