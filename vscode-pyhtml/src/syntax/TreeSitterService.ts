import * as vscode from 'vscode';
import * as path from 'path';
import { Parser, Language, Tree } from 'web-tree-sitter';

export class TreeSitterService {
    private parser: Parser | undefined;
    private language: Language | undefined;

    constructor(private context: vscode.ExtensionContext) { }

    async init() {
        const extensionPath = this.context.extensionPath;
        const treeSitterWasmPath = path.join(extensionPath, 'dist', 'web-tree-sitter.wasm');
        const pyhtmlWasmPath = path.join(extensionPath, 'dist', 'tree-sitter-pyhtml.wasm');

        console.log(`[TreeSitter] Initializing...`);
        console.log(`[TreeSitter] extensionPath: ${extensionPath}`);
        console.log(`[TreeSitter] web-tree-sitter.wasm path: ${treeSitterWasmPath}`);
        console.log(`[TreeSitter] tree-sitter-pyhtml.wasm path: ${pyhtmlWasmPath}`);

        try {
            const fs = await import('fs');

            if (!fs.existsSync(treeSitterWasmPath)) {
                throw new Error(`web-tree-sitter.wasm not found at ${treeSitterWasmPath}`);
            }
            if (!fs.existsSync(pyhtmlWasmPath)) {
                throw new Error(`tree-sitter-pyhtml.wasm not found at ${pyhtmlWasmPath}`);
            }

            console.log(`[TreeSitter] Calling Parser.init...`);
            await Parser.init({
                locateFile: (file: string) => {
                    console.log(`[TreeSitter] Locating file: ${file}`);
                    if (file === 'tree-sitter.wasm') return treeSitterWasmPath;
                    return file;
                }
            });

            this.parser = new Parser();
            console.log(`[TreeSitter] Parser instance created.`);

            console.log(`[TreeSitter] Loading grammar...`);
            const wasmBuffer = fs.readFileSync(pyhtmlWasmPath);
            this.language = await Language.load(wasmBuffer);

            console.log(`[TreeSitter] Setting language...`);
            this.parser.setLanguage(this.language);
            console.log('[TreeSitter] Initialization complete.');
        } catch (e: any) {
            console.error('[TreeSitter] Initialization failed:', e);
            if (e.stack) console.error(e.stack);
            vscode.window.showErrorMessage('Failed to initialize PyHTML syntax highlighter: ' + e.message);
        }
    }

    getParser(): Parser | undefined {
        return this.parser;
    }

    parse(text: string): Tree | null | undefined {
        if (!this.parser) {
            return undefined;
        }
        return this.parser.parse(text);
    }
}
