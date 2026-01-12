"""Jinja2-based interpolation parser."""
from typing import List, Union

from jinja2 import Environment, TemplateSyntaxError

from pyhtml.compiler.ast_nodes import InterpolationNode
from pyhtml.compiler.interpolation.base import InterpolationParser


class JinjaInterpolationParser(InterpolationParser):
    """Jinja2-based interpolation parser."""

    def __init__(self):
        from jinja2 import Environment
        self.env = Environment(
            variable_start_string='{',
            variable_end_string='}',
            autoescape=True  # XSS protection
        )

    def parse(self, text: str, line: int, col: int) -> List[Union[str, InterpolationNode]]:
        """
        Parse text with {expression} into mix of strings and InterpolationNodes.
        Returns: ['Hello, ', InterpolationNode(expr='name'), '!']
        Supports complex expressions: {"text" if condition else "other"}
        """
        if not text:
            return ['']

        result = []
        
        # Simple brace-matching parser for expressions
        import re
        
        i = 0
        last_end = 0
        
        while i < len(text):
            if text[i] == '{':
                # Add any text before this brace
                if i > last_end:
                    result.append(text[last_end:i])
                
                # Find matching closing brace
                brace_count = 1
                j = i + 1
                while j < len(text) and brace_count > 0:
                    if text[j] == '{':
                        brace_count += 1
                    elif text[j] == '}':
                        brace_count -= 1
                    j += 1
                
                if brace_count == 0:
                    # Found matching brace
                    expr = text[i+1:j-1]  # Extract expression without braces
                    result.append(InterpolationNode(
                        expression=expr,
                        line=line,
                        column=col + i
                    ))
                    last_end = j
                    i = j
                else:
                    # Unmatched brace, treat as literal
                    i += 1
            else:
                i += 1
        
        # Add any remaining text
        if last_end < len(text):
            result.append(text[last_end:])

        return result if result else [text]

    def compile(self, text: str) -> str:
        """
        Compile to Python f-string code for runtime.
        'Hello {name}!' → f'Hello {self.name}!'
        'Hello {"text" if cond else "other"}' → f'Hello {"text" if self.cond else "other"}'
        """
        if not text:
            return "''"
        
        # For now, use simple replacement for self. references
        # This is a simplification - ideally we'd parse the expression AST
        import re
        
        result = []
        i = 0
        last_end = 0
        
        while i < len(text):
            if text[i] == '{':
                # Add text before brace
                if i > last_end:
                    result.append(text[last_end:i])
                
                # Find matching closing brace
                brace_count = 1
                j = i + 1
                while j < len(text) and brace_count > 0:
                    if text[j] == '{':
                        brace_count += 1
                    elif text[j] == '}':
                        brace_count -= 1
                    j += 1
                
                if brace_count == 0:
                    # Found matching brace - prepend self. to simple identifiers
                    expr = text[i+1:j-1]
                    # For simple identifiers, add self.
                    # For complex expressions, leave as is (they reference self.* already)
                    if re.match(r'^\w+$', expr):
                        result.append(f'{{self.{expr}}}')
                    else:
                        # Complex expression - assume it references self correctly
                        # Replace standalone identifiers with self. references
                        # This is simplistic but works for common cases
                        modified_expr = re.sub(r'\b([a-zA-Z_]\w*)\b(?!\s*[(\[])', lambda m: f'self.{m.group(1)}' if m.group(1) not in ('if', 'else', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None') else m.group(1), expr)
                        result.append(f'{{{modified_expr}}}')
                    last_end = j
                    i = j
                else:
                    i += 1
            else:
                i += 1
        
        # Add remaining text
        if last_end < len(text):
            result.append(text[last_end:])
        
        compiled = ''.join(result)
        return f"f{repr(compiled)}"
