import * as vscode from 'vscode';
import * as path from 'path';
import { pathToFileURL } from 'url';
import { Parser, Language, Tree } from 'web-tree-sitter';

export class TreeSitterService {
    private parsers: Map<string, Parser> = new Map();
    private languages: Map<string, Language> = new Map();

    constructor(private context: vscode.ExtensionContext) { }

    async init() {
        const extensionPath = this.context.extensionPath;
        const treeSitterWasmPath = path.join(extensionPath, 'dist', 'web-tree-sitter.wasm');

        // Paths for languages
        const pyhtmlWasmPath = path.join(extensionPath, 'dist', 'tree-sitter-pyhtml.wasm');
        const pythonWasmPath = path.join(extensionPath, 'dist', 'tree-sitter-python.wasm');

        // Convert to file:// URLs which web-tree-sitter requires in Node.js
        const treeSitterWasmUrl = pathToFileURL(treeSitterWasmPath).href;

        console.log(`[TreeSitter] Initializing...`);

        try {
            const fs = await import('fs');

            if (!fs.existsSync(treeSitterWasmPath)) {
                throw new Error(`web-tree-sitter.wasm not found at ${treeSitterWasmPath}`);
            }

            await Parser.init({
                locateFile: (file: string, _scriptDir: string) => {
                    return treeSitterWasmPath;
                }
            });

            // Load PyHTML
            if (fs.existsSync(pyhtmlWasmPath)) {
                console.log(`[TreeSitter] Loading pyhtml form ${pyhtmlWasmPath}`);
                const pyhtmlLang = await Language.load(fs.readFileSync(pyhtmlWasmPath));
                const pyhtmlParser = new Parser();
                pyhtmlParser.setLanguage(pyhtmlLang);
                this.parsers.set('pyhtml', pyhtmlParser);
                this.languages.set('pyhtml', pyhtmlLang);
            } else {
                console.error(`[TreeSitter] tree-sitter-pyhtml.wasm not found`);
            }

            // Load Python
            if (fs.existsSync(pythonWasmPath)) {
                console.log(`[TreeSitter] Loading python from ${pythonWasmPath}`);
                const pythonLang = await Language.load(fs.readFileSync(pythonWasmPath));
                const pythonParser = new Parser();
                pythonParser.setLanguage(pythonLang);
                this.parsers.set('python', pythonParser);
                this.languages.set('python', pythonLang);
            } else {
                console.warn(`[TreeSitter] tree-sitter-python.wasm not found at ${pythonWasmPath}. Python semantic tokens will be disabled.`);
            }

            console.log('[TreeSitter] Initialization complete.');
        } catch (e: any) {
            console.error('[TreeSitter] Initialization failed:', e);
            if (e.stack) console.error(e.stack);
            vscode.window.showErrorMessage('Failed to initialize PyHTML syntax highlighter: ' + e.message);
        }
    }

    getParser(lang: string): Parser | undefined {
        return this.parsers.get(lang);
    }

    getLanguage(lang: string): Language | undefined {
        return this.languages.get(lang);
    }

    parse(text: string, lang: 'pyhtml' | 'python'): Tree | undefined {
        const parser = this.parsers.get(lang);
        if (!parser) return undefined;
        return parser.parse(text) || undefined;
    }
}
