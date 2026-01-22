---
name: pyhtml-lsp
description: Guides development and modification of the PyHTML Language Server. Use when working on LSP features like diagnostics, hover, completion, or go-to-definition for .pyhtml files.
---

# PyHTML LSP Development

This skill provides guidance for modifying the PyHTML Language Server Protocol (LSP) implementation.

## Project Structure

| Path | Description |
|------|-------------|
| `lsp/src/pyhtml_lsp/server.py` | Main LSP server logic |
| `tree-sitter-pyhtml/grammar.js` | Tree-sitter grammar for syntax highlighting |
| `vscode-pyhtml/` | VSCode extension that uses the LSP |

## Key Components in `server.py`

### `PyHTMLDocument` Class
Represents a parsed `.pyhtml` document. Key methods:
- `_validate()` - Basic validation (separator, path directive)
- `_validate_event_handlers()` - Validates `@event` and `$directive` attributes
- `get_section(line)` - Returns `'html'`, `'python'`, `'directive'`, or `'separator'`
- `get_event_attr_at(line, char)` - Returns attribute info at cursor position
- `get_interpolation_at(line, char)` - Returns interpolation `{...}` info at cursor

### LSP Feature Handlers
- `@server.feature('textDocument/hover')` - Hover documentation
- `@server.feature('textDocument/completion')` - Auto-completions
- `@server.feature('textDocument/definition')` - Go-to-definition
- `@server.feature('textDocument/semanticTokens/full')` - Semantic highlighting

## Common Tasks

### Adding a New Directive or Attribute
1. Update the regex in `_validate_event_handlers()` if needed
2. Add validation logic for the new attribute
3. Add hover documentation in the `hover_docs` dict in `hover()`
4. Add completion item in `completions()`

### Adding Event Modifiers
1. Add modifier to `valid_modifiers` set in `_validate_event_handlers()`
2. Update hover logic to handle the modifier

### Updating Syntax Highlighting
1. Modify `tree-sitter-pyhtml/grammar.js`
2. Rebuild the WASM file: `cd tree-sitter-pyhtml && npx tree-sitter generate && npx tree-sitter build --wasm`

## Attribute Regex Pattern

The regex for matching special attributes:
```python
r'([@$][\w\.]+)="([^"]*)"'
```
- `@event.modifier1.modifier2="handler"` - Event handlers with modifiers
- `$directive="value"` - Directives like `$if`, `$for`, `$bind`

## Testing

Run LSP tests:
```bash
python3 test_lsp_interactivity.py
```

## Debugging

LSP logs are written to `/tmp/pyhtml-lsp.log`. Check this file for errors during development.

## Decision Tree

```
Is this about syntax highlighting?
├─ Yes → Modify grammar.js, rebuild WASM
└─ No → Modify server.py
         ├─ Add new attribute → Update regex, validation, hover, completion
         ├─ Fix validation → Check _validate_event_handlers()
         ├─ Fix hover → Check hover() function
         └─ Fix completion → Check completions() function
```
