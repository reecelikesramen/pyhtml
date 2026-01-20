import * as vscode from 'vscode';
import { TreeSitterService } from './TreeSitterService';

// Legend must match the classification we use
export const tokenTypesLegend = [
    'keyword', 'variable', 'string', 'function', 'class', 'method', 'comment',
    'type', 'parameter', 'property', 'operator', 'decorator', 'macro'
];

export const tokenModifiersLegend = [
    'declaration', 'documentation', 'readonly', 'static', 'abstract', 'async'
];

export const legend = new vscode.SemanticTokensLegend(tokenTypesLegend, tokenModifiersLegend);

export class PyHTMLSemanticTokenProvider implements vscode.DocumentSemanticTokensProvider {
    constructor(private treeSitterService: TreeSitterService) { }

    async provideDocumentSemanticTokens(
        document: vscode.TextDocument,
        token: vscode.CancellationToken
    ): Promise<vscode.SemanticTokens> {
        // 1. Parse PyHTML structure
        const pyhtmlTree = this.treeSitterService.parse(document.getText(), 'pyhtml');
        if (!pyhtmlTree) {
            return new vscode.SemanticTokens(new Uint32Array(0));
        }

        const builder = new vscode.SemanticTokensBuilder(legend);

        // Collect Python regions
        const pythonRegions: { start: number; end: number; startPos: vscode.Position }[] = [];

        // specific visitor to collect regions and tokenize structure
        const visitPyHTML = (node: any) => {
            const type = node.type;

            if (type === 'python_section') {
                // The content of the python section is everything after "---"
                // We need to find the "---" separator node?
                // Actually, the structure usually has a separator child and then content?
                // Based on grammar, it might just be the node range minus the separator.
                // Let's assume the whole node is the section.
                // We should check if it has a separator child.
                const separator = node.children.find((c: any) => c.type === 'separator' || c.text === '---');
                if (separator) {
                    // Content starts after separator
                    pythonRegions.push({
                        start: separator.endIndex,
                        end: node.endIndex,
                        startPos: new vscode.Position(separator.endPosition.row, separator.endPosition.column)
                    });
                }
            } else if (type === 'attribute_content') {
                // Check parent for special attribute
                const isSpecial = node.parent?.parent?.children.some((c: any) =>
                    c.type === 'special_attribute_name' || (c.type === 'attribute_name' && c.text.startsWith('@'))
                );
                if (isSpecial) {
                    // Determine content inside quotes
                    // attribute_content usually includes the quotes? Or just inner?
                    // Tree-sitter-pyhtml definition of attribute_content usually matches "..." or """..."""
                    // We need to strip quotes.
                    const text = node.text;
                    if (text.startsWith('"""') && text.endsWith('"""')) {
                        pythonRegions.push({
                            start: node.startIndex + 3,
                            end: node.endIndex - 3,
                            startPos: document.positionAt(node.startIndex + 3)
                        });
                    } else if (text.startsWith('"') && text.endsWith('"')) {
                        pythonRegions.push({
                            start: node.startIndex + 1,
                            end: node.endIndex - 1,
                            startPos: document.positionAt(node.startIndex + 1)
                        });
                    }
                }
            } else if (type === 'interpolation') {
                // { content }
                // Strip braces
                pythonRegions.push({
                    start: node.startIndex + 1,
                    end: node.endIndex - 1,
                    startPos: document.positionAt(node.startIndex + 1)
                });
            }

            // Tokenize PyHTML specific bits
            if (type === 'tag_name') {
                this.addToken(builder, node, 'class');
            } else if (type === 'attribute_name') {
                this.addToken(builder, node, 'property');
            } else if (type === 'special_attribute_name') {
                this.addToken(builder, node, 'macro');
            } else if (type === 'keyword_directive') {
                this.addToken(builder, node, 'keyword');
            }
            // Note: We deliberately skip 'separator' and 'comment' here to let TextMate handle them, 
            // or we could add them. Let's add them for consistency.
            else if (type === 'comment') {
                this.addToken(builder, node, 'comment');
            } else if (type === 'separator') {
                this.addToken(builder, node, 'keyword');
            }

            for (const child of node.children) {
                visitPyHTML(child);
            }
        };

        visitPyHTML(pyhtmlTree.rootNode);

        // 2. Parse and Tokenize Python regions
        const pythonParser = this.treeSitterService.getParser('python');
        if (pythonParser) {
            const fullText = document.getText();

            for (const region of pythonRegions) {
                if (region.start >= region.end) continue;

                const code = fullText.substring(region.start, region.end);

                // For attributes, we might want to dedent? 
                // But for now, let's parse as is.
                const tree = pythonParser.parse(code);
                if (!tree) continue;

                this.visitPythonNode(tree.rootNode, builder, region.startPos);
            }
        }

        return builder.build();
    }

    private addToken(builder: vscode.SemanticTokensBuilder, node: any, type: string, modifiers?: string[]) {
        const start = new vscode.Position(node.startPosition.row, node.startPosition.column);
        const end = new vscode.Position(node.endPosition.row, node.endPosition.column);
        const range = new vscode.Range(start, end);
        builder.push(range, type, modifiers);
    }

    private visitPythonNode(node: any, builder: vscode.SemanticTokensBuilder, basePos: vscode.Position) {
        // Adjust node position by basePos
        // Note: Tree-sitter positions are 0-based row/col.
        // If we map substring, the node.row is relative to start of string.
        // We need to map (node.row, node.col) to (basePos.line + node.row, ...)
        // BUT! If basePos is in middle of line (e.g. at `foo="`), then `node.row=0` matches basePos.line.
        // `node.col` for row 0 is relative to start of string (offset from basePos.character).
        // `node.col` for row > 0 is absolute column in that line (because multiline string content is indented in file).

        // Wait, if we extract `code = substring(...)`, the indentation is preserved.
        // So `node.col` on row > 0 will include the file indentation.
        // Correct logic:
        // Absolute Line = basePos.line + node.row
        // Absolute Col = (node.row === 0 ? basePos.character + node.col : node.col)

        const type = this.mapPythonType(node.type);
        if (type) {
            const startLine = basePos.line + node.startPosition.row;
            const startCol = (node.startPosition.row === 0) ? basePos.character + node.startPosition.column : node.startPosition.column;

            const endLine = basePos.line + node.endPosition.row;
            const endCol = (node.endPosition.row === 0) ? basePos.character + node.endPosition.column : node.endPosition.column;

            const range = new vscode.Range(startLine, startCol, endLine, endCol);
            builder.push(range, type);
        }

        for (const child of node.children) {
            this.visitPythonNode(child, builder, basePos);
        }
    }

    private mapPythonType(type: string): string | undefined {
        // Map tree-sitter-python nodes to semantic token types
        switch (type) {
            case 'identifier': return 'variable';
            case 'string': return 'string';
            case 'integer':
            case 'float': return 'number';
            case 'comment': return 'comment';
            case 'function_definition': return undefined; // Let children (name) handle it
            case 'call': return undefined; // Let children handle it
            case 'attribute': return 'property';
            case 'class_definition': return undefined;
            // Keywords
            case 'import_from_statement':
            case 'import_statement':
            case 'return_statement':
            case 'if_statement':
            case 'for_statement':
                // Specific keywords often identified by node type or text, 
                // but tree-sitter-python usually has explicit node types for keywords?
                // Actually, newer grammars use anonymous nodes for keywords (e.g. "if").
                // We might need to check literal text or specific node types.
                // Let's rely on specific named nodes first.

                // Actually, tree-sitter-python often uses 'identifier' for everything
                // and we rely on parent to distinguish.
                // e.g. function identifier -> function
                // call -> function
                return undefined;
        }

        // Heuristics for identifiers based on parent
        if (type === 'identifier') {
            // Check context
            return 'variable'; // Default
        }

        // Keywords are often anonymous nodes in tree-sitter, we can't easily detecting them 
        // unless we check the type against a list of keywords or string literals.
        // Tree-sitter often names them like "return", "if", "else" if they are named nodes.
        // If they are anonymous (double quotes in grammar), they don't have a named type.
        // But `node.type` is the string.
        const keywords = ['def', 'class', 'import', 'from', 'return', 'if', 'else', 'elif', 'for', 'in', 'while', 'try', 'except', 'pass', 'raise', 'with', 'as', 'assert', 'break', 'continue', 'lambda', 'global', 'nonlocal', 'del', 'yield', 'async', 'await'];
        if (keywords.includes(type)) {
            return 'keyword';
        }

        if (type === 'self') return 'variable';
        if (type === 'true' || type === 'false' || type === 'none') return 'keyword';

        return undefined;
    }
}
