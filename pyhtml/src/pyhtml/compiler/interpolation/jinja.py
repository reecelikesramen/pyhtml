"""Jinja2-based interpolation parser."""
from typing import List, Union

from jinja2 import Environment, TemplateSyntaxError

from pyhtml.compiler.ast_nodes import InterpolationNode
from pyhtml.compiler.interpolation.base import InterpolationParser


import ast

class JinjaInterpolationParser(InterpolationParser):
    """Jinja2-based interpolation parser."""

    def __init__(self):
        from jinja2 import Environment
        self.env = Environment(
            variable_start_string='{',
            variable_end_string='}',
            autoescape=True  # XSS protection
        )

    def _is_valid_python(self, text: str) -> bool:
        """Check if text is valid Python expression (or with format spec)."""
        stripped = text.strip()
        
        # 1. Try simple parse
        try:
            ast.parse(stripped, mode='eval')
            return True
        except SyntaxError:
            pass

        # 2. CSS-like check: If unparseable and contains semicolon, assume CSS
        if ';' in text:
            return False

        # 3. Format specifier check: Find top-level colon
        balance = 0
        quote = None
        split_idx = -1
        
        for i, char in enumerate(text):
            if quote:
                if char == quote:
                    if i > 0 and text[i-1] != '\\':
                        quote = None
            else:
                if char in "\"'":
                    quote = char
                elif char in "{[(":
                    balance += 1
                elif char in "}])":
                    balance -= 1
                elif char == ':' and balance == 0:
                    split_idx = i
                    break
        
        if split_idx != -1:
            # We strip the expression part to allow "{ x :.2f }"
            expr = text[:split_idx].strip()
            try:
                ast.parse(expr, mode='eval')
                return True
            except SyntaxError:
                pass
        
        return False

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
                    
                    if self._is_valid_python(expr):
                        result.append(InterpolationNode(
                            expression=expr,
                            line=line,
                            column=col + i
                        ))
                    else:
                        # Treat as literal
                        result.append(text[i:j])
                        
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
                    # Found matching brace 
                    # CHECK IF VALID PYTHON before trying to compile
                    # (Though compile is usually called on text that parse() has already mostly validated,
                    # parse() returns nodes for valid interpolations.
                    # Wait, template codegen calls compile() on text_content of nodes.
                    # If parse() returned literal text for CSS, then compile() will see the curly braces!
                    # And compile() iterates braces independently.
                    # So compile() MUST also respect the validity check!)
                    
                    expr = text[i+1:j-1]
                    if self._is_valid_python(expr):
                        # Prepend self. to simple identifiers
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
                    else:
                        # Literal (CSS etc)
                        result.append(text[i:j])
                        
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
