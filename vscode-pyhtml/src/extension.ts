import * as path from 'path';
import { workspace, ExtensionContext, window } from 'vscode';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
} from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: ExtensionContext) {
    console.log('PyHTML extension activating...');

    // Get Python path from settings
    const config = workspace.getConfiguration('pyhtml');
    // HARDCODED for testing: use the project's venv python
    const pythonPath = '/Users/rholmdahl/projects/pyhtml/.venv/bin/python'; 
    // const pythonPath = config.get<string>('pythonPath') || 'python3';

    // Path to LSP server script
    // Assumes lsp/ is adjacent to vscode-pyhtml/
    const serverScript = context.asAbsolutePath(
        path.join('..', 'lsp', 'pyhtml_lsp_server')
    );

    console.log('LSP server script:', serverScript);

    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/41df94cc-62d1-43cd-920c-d1dbf5d35a88',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'vscode-pyhtml/src/extension.ts:26',message:'Extension activating, server options',data:{pythonPath, serverScript},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H1'})}).catch(()=>{});
    // #endregion

    // Server options - how to start the server
    const serverOptions: ServerOptions = {
        command: pythonPath,
        args: [serverScript],
        options: {
            env: { ...process.env }
        }
    };

    // Client options - what to send to the server
    const clientOptions: LanguageClientOptions = {
        documentSelector: [
            { scheme: 'file', language: 'pyhtml' }
        ],
        synchronize: {
            fileEvents: workspace.createFileSystemWatcher('**/*.pyhtml')
        },
        // Enable semantic tokens
        initializationOptions: {}
    };

    // Create the language client
    client = new LanguageClient(
        'pyhtmlLanguageServer',
        'PyHTML Language Server',
        serverOptions,
        clientOptions
    );

    // Start the client (and server)
    client.start().then(() => {
        console.log('PyHTML language server started');
        window.showInformationMessage('PyHTML language server is running');
    }).catch(err => {
        console.error('Failed to start PyHTML language server:', err);
        window.showErrorMessage('Failed to start PyHTML language server: ' + err);
    });
}

export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    return client.stop();
}