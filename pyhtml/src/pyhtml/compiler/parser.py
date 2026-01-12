"""Main PyHTML parser orchestrator."""
import ast
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

from pyhtml.compiler.ast_nodes import ParsedPyHTML, SpecialAttribute, TemplateNode
from pyhtml.compiler.attributes.base import AttributeParser
from pyhtml.compiler.attributes.events import EventAttributeParser
from pyhtml.compiler.directives.base import DirectiveParser
from pyhtml.compiler.directives.path import PathDirectiveParser
from pyhtml.compiler.interpolation.jinja import JinjaInterpolationParser


class TemplateHTMLParser(HTMLParser):
    """HTML parser that builds TemplateNode tree with special attribute support."""

    def __init__(self, attribute_parsers: List[AttributeParser], interpolation_parser):
        super().__init__()
        self.attribute_parsers = attribute_parsers
        self.interpolation_parser = interpolation_parser
        self.nodes: List[TemplateNode] = []
        self.stack: List[TemplateNode] = []
        self.current_line = 1
        self.current_col = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        """Handle opening tag."""
        regular_attrs, special_attrs = self._parse_attributes(attrs)

        node = TemplateNode(
            tag=tag,
            attributes=regular_attrs,
            special_attributes=special_attrs,
            line=self.current_line,
            column=self.current_col
        )

        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.nodes.append(node)

        self.stack.append(node)

    def handle_endtag(self, tag: str):
        """Handle closing tag."""
        if self.stack and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_data(self, data: str):
        """Handle text content."""
        if not data.strip():
            return

        # Parse interpolations
        parts = self.interpolation_parser.parse(data, self.current_line, self.current_col)

        # Create text nodes for each part
        for part in parts:
            if isinstance(part, str):
                if part.strip():
                    text_node = TemplateNode(
                        tag=None,
                        text_content=part,
                        line=self.current_line,
                        column=self.current_col
                    )
                    if self.stack:
                        self.stack[-1].children.append(text_node)
                    else:
                        self.nodes.append(text_node)
            else:
                # InterpolationNode - wrap in text node
                text_node = TemplateNode(
                    tag=None,
                    text_content=None,
                    line=part.line,
                    column=part.column
                )
                text_node.special_attributes = [part]  # Store interpolation as special attribute
                if self.stack:
                    self.stack[-1].children.append(text_node)
                else:
                    self.nodes.append(text_node)

    def _parse_attributes(self, attrs: List[Tuple[str, Optional[str]]]) -> Tuple[dict, List[SpecialAttribute]]:
        """Separate regular attrs from special ones."""
        regular = {}
        special = []

        for name, value in attrs:
            if value is None:
                value = ""
            parsed = False
            for parser in self.attribute_parsers:
                if parser.can_parse(name):
                    attr = parser.parse(name, value, self.current_line, self.current_col)
                    if attr:
                        special.append(attr)
                    parsed = True
                    break

            if not parsed:
                regular[name] = value

        return regular, special


class PyHTMLParser:
    """Main parser orchestrator."""

    def __init__(self):
        # Directive registry
        self.directive_parsers: List[DirectiveParser] = [
            PathDirectiveParser(),
            # Future: LayoutDirectiveParser(), etc.
        ]

        # Attribute parser chain
        self.attribute_parsers = [
            EventAttributeParser(),
            # Future: BindAttributeParser(), ConditionalParser(), etc.
        ]

        # Interpolation parser (pluggable)
        self.interpolation_parser = JinjaInterpolationParser()

    def parse_file(self, file_path: Path) -> ParsedPyHTML:
        """Parse a .pyhtml file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return self.parse(content, str(file_path))

    def parse(self, content: str, file_path: str = "") -> ParsedPyHTML:
        """Parse PyHTML content."""
        lines = content.split('\n')
        
        # Split into sections: directives/template and Python code
        python_start = -1
        for i, line in enumerate(lines):
            if line.strip() == '---':
                python_start = i
                break

        # Parse directives (before ---)
        directives = []
        template_lines = []
        
        if python_start >= 0:
            directive_section = '\n'.join(lines[:python_start])
            python_section = '\n'.join(lines[python_start + 1:])
        else:
            directive_section = content
            python_section = ""

        # Parse directives
        for line_num, line in enumerate(directive_section.split('\n'), 1):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('---'):
                continue

            # Check if it's a directive
            for parser in self.directive_parsers:
                if parser.can_parse(line_stripped):
                    directive = parser.parse(line_stripped, line_num, 0)
                    if directive:
                        directives.append(directive)
                        break
            else:
                # Not a directive, part of template
                template_lines.append(line)

        # Parse template HTML
        template_html = '\n'.join(template_lines)
        html_parser = TemplateHTMLParser(self.attribute_parsers, self.interpolation_parser)
        html_parser.feed(template_html)
        template_nodes = html_parser.nodes

        # Parse Python code
        python_ast = None
        if python_section.strip():
            try:
                python_ast = ast.parse(python_section)
            except SyntaxError:
                pass  # Will be caught later

        return ParsedPyHTML(
            directives=directives,
            template=template_nodes,
            python_code=python_section,
            python_ast=python_ast,
            file_path=file_path
        )
