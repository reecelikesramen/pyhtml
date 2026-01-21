import { TransportManager, TransportConfig } from './transport-manager';
import { DOMUpdater } from './dom-updater';
import { ServerMessage, ClientMessage, EventData, RelocateMessage, StackFrame } from './transports';



export interface PyHTMLConfig extends TransportConfig {
    /** Auto-initialize on DOMContentLoaded */
    autoInit?: boolean;
}

const DEFAULT_CONFIG: PyHTMLConfig = {
    autoInit: true,
    enableWebTransport: true,
    enableWebSocket: true,
    enableHTTP: true
};

/**
 * Main PyHTML Application class.
 */
export class PyHTMLApp {
    private transport: TransportManager;
    private updater: DOMUpdater;
    private initialized = false;
    private config: PyHTMLConfig;
    private siblingPaths: string[] = [];
    private pathRegexes: RegExp[] = [];
    private pjaxEnabled = false;
    private statusOverlay: HTMLElement | null = null;
    private isConnected = false;

    constructor(config: Partial<PyHTMLConfig> = {}) {
        this.config = { ...DEFAULT_CONFIG, ...config };
        this.transport = new TransportManager(this.config);
        this.updater = new DOMUpdater();
    }

    /**
     * Initialize the PyHTML application.
     */
    async init(): Promise<void> {
        if (this.initialized) return;
        this.initialized = true;

        // Setup message handling
        this.transport.onMessage((msg) => this.handleMessage(msg));
        this.transport.onStatusChange((connected) => this.handleStatusChange(connected));

        // Create UI
        this.createStatusOverlay();
        this.handleStatusChange(false); // Initial state

        // Connect transport with fallback
        try {
            await this.transport.connect();
        } catch (e) {
            console.error('PyHTML: Failed to connect:', e);
        }

        // Load SPA metadata and setup navigation
        this.loadSPAMetadata();
        this.setupSPANavigation();

        // Setup event interception
        this.setupEventInterceptors();

        console.log(`PyHTML: Initialized (transport: ${this.transport.getActiveTransport()}, spa_paths: ${this.siblingPaths.length}, pjax: ${this.pjaxEnabled})`);
    }

    /**
     * Load SPA navigation metadata from injected script tag.
     */
    private loadSPAMetadata(): void {
        const metaScript = document.getElementById('_pyhtml_spa_meta');
        if (metaScript) {
            try {
                const meta = JSON.parse(metaScript.textContent || '{}');
                this.siblingPaths = meta.sibling_paths || [];
                this.pjaxEnabled = !!meta.enable_pjax;
                // Convert path patterns to regexes for matching
                this.pathRegexes = this.siblingPaths.map(p => this.patternToRegex(p));
            } catch (e) {
                console.warn('PyHTML: Failed to parse SPA metadata', e);
            }
        }
    }

    private createStatusOverlay(): void {
        this.statusOverlay = document.createElement('div');
        this.statusOverlay.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 14px;
            z-index: 10000;
            display: none;
            transition: opacity 0.3s;
            pointer-events: none;
        `;
        document.body.appendChild(this.statusOverlay);
    }

    private handleStatusChange(connected: boolean): void {
        this.isConnected = connected;
        if (this.statusOverlay) {
            if (connected) {
                this.statusOverlay.style.display = 'none';
            } else {
                this.statusOverlay.textContent = 'Connection Lost - Reconnecting...';
                this.statusOverlay.style.display = 'block';
            }
        }
    }

    /**
     * Convert route pattern like '/a/:id' to regex.
     */
    private patternToRegex(pattern: string): RegExp {
        // Escape special regex chars except for our placeholders
        let regex = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
        // Replace :param:type or :param with capture groups
        regex = regex.replace(/:(\w+)(:\w+)?/g, '([^/]+)');
        // Replace {param:type} or {param} with capture groups
        regex = regex.replace(/\{(\w+)(:\w+)?\}/g, '([^/]+)');
        return new RegExp(`^${regex}$`);
    }

    /**
     * Check if a path matches any sibling path pattern.
     */
    private isSiblingPath(path: string): boolean {
        return this.pathRegexes.some(regex => regex.test(path));
    }

    /**
     * Setup SPA navigation for sibling paths.
     */
    private setupSPANavigation(): void {
        // Handle browser back/forward - establish this ALWAYS to support navigating
        // back to a valid SPA page from a 404 or other page.
        window.addEventListener('popstate', () => {
            this.sendRelocate(window.location.pathname + window.location.search);
        });

        if (this.siblingPaths.length === 0 && !this.pjaxEnabled) return;

        // Intercept link clicks
        document.addEventListener('click', (e) => {
            const link = (e.target as Element).closest('a[href]') as HTMLAnchorElement | null;
            if (!link) return;

            // Only intercept same-origin links
            if (link.origin !== window.location.origin) return;

            // Ignore special links
            if (link.hasAttribute('download') || link.target === '_blank') return;

            // Check if matches criteria
            let shouldIntercept = false;

            if (this.pjaxEnabled) {
                // If PJAX enabled, intercept all internal paths (unless manually opted out maybe?)
                // For now, intercept everything same-origin
                shouldIntercept = true;
            } else if (this.isSiblingPath(link.pathname)) {
                // Sibling path logic
                shouldIntercept = true;
            }

            if (shouldIntercept) {
                e.preventDefault();
                this.navigateTo(link.pathname + link.search);
            }
        });
    }

    /**
     * Navigate to a sibling path using SPA navigation.
     */
    navigateTo(path: string): void {
        if (!this.isConnected) {
            console.warn('PyHTML: Navigation blocked - Offline');
            // Flash the overlay or show specific alert?
            if (this.statusOverlay) {
                this.statusOverlay.style.backgroundColor = 'rgba(200, 0, 0, 0.9)';
                this.statusOverlay.textContent = 'Cannot navigate - Offline';
                setTimeout(() => {
                    this.handleStatusChange(this.isConnected); // Reset style
                    if (this.statusOverlay) this.statusOverlay.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
                }, 1500);
            }
            return;
        }

        history.pushState({}, '', path);
        this.sendRelocate(path);
    }

    /**
     * Send relocate message to server.
     */
    private sendRelocate(path: string): void {
        const message: RelocateMessage = {
            type: 'relocate',
            path
        };
        this.transport.send(message);
    }

    /**
     * Setup DOM event interceptors.
     */
    private setupEventInterceptors(): void {
        // Click events
        document.addEventListener('click', (e) => {
            const target = (e.target as Element).closest('[data-on-click]');
            if (target) {
                e.preventDefault();
                const handler = target.getAttribute('data-on-click');
                if (handler) {
                    this.sendEvent(handler, {
                        type: 'click',
                        id: target.id,
                        value: (target as HTMLInputElement).value,
                        args: this.getArgs(target)
                    });
                }
            }
        });

        // Submit events
        document.addEventListener('submit', async (e) => {
            const target = (e.target as Element).closest('[data-on-submit]');
            if (target) {
                e.preventDefault();
                const handler = target.getAttribute('data-on-submit');
                if (handler) {
                    const form = target as HTMLFormElement;
                    // Collect form data
                    const formData = new FormData(form);
                    const data: Record<string, any> = {};

                    // Handle regular fields
                    formData.forEach((value, key) => {
                        if (value instanceof File) {
                            // Skip files here, handle them below to support async reading
                        } else {
                            data[key] = value.toString();
                        }
                    });

                    // Handle file inputs: Upload via HTTP endpoint first
                    const fileInputs = form.querySelectorAll('input[type="file"]');
                    const uploadPromises: Promise<void>[] = [];

                    fileInputs.forEach((input) => {
                        const fileInput = input as HTMLInputElement;
                        const name = fileInput.name;
                        if (!name) return;

                        if (fileInput.files && fileInput.files.length > 0) {
                            const file = fileInput.files[0];

                            // Client-side Validation

                            // Check size
                            const maxSizeAttr = fileInput.getAttribute('max-size');
                            if (maxSizeAttr) {
                                let maxSize = parseInt(maxSizeAttr);
                                const lower = maxSizeAttr.toLowerCase();
                                if (lower.endsWith('kb') || lower.endsWith('k')) maxSize = parseInt(lower) * 1024;
                                else if (lower.endsWith('mb') || lower.endsWith('m')) maxSize = parseInt(lower) * 1024 * 1024;
                                else if (lower.endsWith('gb') || lower.endsWith('g')) maxSize = parseInt(lower) * 1024 * 1024 * 1024;

                                if (file.size > maxSize) {
                                    const msg = `File is too large. Max size is ${maxSizeAttr}.`;
                                    alert(msg);
                                    uploadPromises.push(Promise.reject(msg));
                                    return;
                                }
                            }

                            // Check type (if accept is set, though browser handles picker)
                            const accept = fileInput.accept;
                            if (accept) {
                                // Simple check for basic types if needed
                                // Skipping complex MIME parsing for now as server validates strictly
                            }

                            const uploadFormData = new FormData();
                            uploadFormData.append(name, file);

                            const uploadPromise = new Promise<void>((resolve, reject) => {
                                const xhr = new XMLHttpRequest();
                                xhr.open('POST', '/_pyhtml/upload');

                                // Add Upload Token
                                const tokenMeta = document.querySelector('meta[name="pyhtml-upload-token"]');
                                if (tokenMeta) {
                                    const token = tokenMeta.getAttribute('content');
                                    if (token) {
                                        xhr.setRequestHeader('X-Upload-Token', token);
                                    }
                                }

                                // Progress handling
                                // Throttle progress updates to avoid flooding
                                let lastProgressTime = 0;
                                xhr.upload.onprogress = (e) => {
                                    if (e.lengthComputable) {
                                        const now = Date.now();
                                        if (now - lastProgressTime >= 100) { // 100ms throttle
                                            lastProgressTime = now;
                                            const percent = e.loaded / e.total;

                                            // Send directly to avoid detached DOM node issues if re-rendered
                                            const handler = fileInput.getAttribute('data-on-upload-progress');
                                            if (handler) {
                                                this.sendEvent(handler, {
                                                    type: 'upload-progress',
                                                    id: fileInput.id,
                                                    progress: percent,
                                                    args: this.getArgs(fileInput)
                                                });
                                            }
                                        }
                                    }
                                };

                                xhr.onload = () => {
                                    if (xhr.status >= 200 && xhr.status < 300) {
                                        try {
                                            const result = JSON.parse(xhr.responseText);
                                            if (result[name]) {
                                                data[name] = {
                                                    _upload_id: result[name],
                                                    name: file.name,
                                                    type: file.type,
                                                    size: file.size
                                                };
                                                resolve();
                                            } else {
                                                console.error('PyHTML: Upload failed, no ID returned', result);
                                                reject(new Error('No ID returned'));
                                            }
                                        } catch (e) {
                                            reject(e);
                                        }
                                    } else {
                                        // Handle server errors (e.g. 413 Payload Too Large)
                                        const msg = `Upload failed: ${xhr.status} ${xhr.statusText}`;
                                        console.error('PyHTML: Upload failed', xhr.status, xhr.responseText);
                                        alert(msg); // Provide immediate feedback
                                        reject(new Error(msg));
                                    }
                                };

                                xhr.onerror = () => reject(xhr.statusText);
                                xhr.send(uploadFormData);
                            });

                            uploadPromises.push(uploadPromise);
                        }
                    });

                    // Wait for all uploads
                    console.log('PyHTML: Waiting for uploads...');
                    try {
                        await Promise.all(uploadPromises);
                        console.log('PyHTML: Uploads complete. Sending submit event.');
                    } catch (e) {
                        console.error('PyHTML: Upload validation failed', e);
                        return;
                    }

                    this.sendEvent(handler, {
                        type: 'submit',
                        id: target.id,
                        formData: data,
                        args: this.getArgs(target)
                    });
                }
            }
        });

        // Input events (debounced for performance)
        let inputTimeout: number | undefined;
        document.addEventListener('input', (e) => {
            const target = (e.target as Element).closest('[data-on-input]');
            if (target) {
                clearTimeout(inputTimeout);
                inputTimeout = window.setTimeout(() => {
                    const handler = target.getAttribute('data-on-input');
                    if (handler) {
                        this.sendEvent(handler, {
                            type: 'input',
                            id: target.id,
                            value: (target as HTMLInputElement).value,
                            args: this.getArgs(target)
                        });
                    }
                }, 150); // 150ms debounce
            }
        });

        // Change events
        document.addEventListener('change', (e) => {
            const target = (e.target as Element).closest('[data-on-change]');
            if (target) {
                const handler = target.getAttribute('data-on-change');
                if (handler) {
                    this.sendEvent(handler, {
                        type: 'change',
                        id: target.id,
                        value: (target as HTMLInputElement).value,
                        checked: (target as HTMLInputElement).checked,
                        args: this.getArgs(target)
                    });
                }
            }
        });

    }

    /**
     * Collect data-arg-* attributes from element.
     */
    private getArgs(element: Element): Record<string, unknown> {
        const args: Record<string, unknown> = {};
        if (element instanceof HTMLElement) {
            for (const key in element.dataset) {
                if (key.startsWith('arg')) {
                    // dataset keys are camelCase (data-arg-0 -> arg0)
                    // Values are JSON encoded
                    try {
                        args[key] = JSON.parse(element.dataset[key] || 'null');
                    } catch (e) {
                        console.warn('PyHTML: Failed to parse arg', key, element.dataset[key]);
                        args[key] = element.dataset[key];
                    }
                }
            }
        }
        return args;
    }

    /**
     * Send an event to the server.
     */
    sendEvent(handler: string, data: EventData): void {
        const message: ClientMessage = {
            type: 'event',
            handler,
            path: window.location.pathname + window.location.search,
            data
        };
        this.transport.send(message);
    }

    /**
     * Handle incoming server message.
     */
    private loadedSources = new Set<string>();

    private getVirtualUrl(filename: string): string {
        // Generate a consistent virtual URL for a filename
        // Must include origin to ensure Chrome treats it as a full URL for linking
        const encoded = btoa(filename).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        // Append clean filename to URL so Chrome displays it in stack trace
        const cleanName = filename.split(/[/\\]/).pop() || 'unknown';
        return `${window.location.origin}/_pyhtml/file/${encoded}/${cleanName}`;
    }

    private async handleErrorTrace(errorMessage: string, trace: StackFrame[]) {
        // Load sources for frames
        const filesToLoad = new Set<string>();
        for (const frame of trace) {
            if (!this.loadedSources.has(frame.filename)) {
                filesToLoad.add(frame.filename);
            }
        }


        await Promise.all(Array.from(filesToLoad).map(async (filename) => {
            try {
                const virtualUrl = this.getVirtualUrl(filename);

                // Fetch content
                const url = `/_pyhtml/source?path=${encodeURIComponent(filename)}`;
                const resp = await fetch(url);
                if (resp.ok) {
                    const content = await resp.text();

                    // Inject the raw Python/PyHTML source with sourceURL only
                    // The script has "syntax errors" (it's Python, not JS) but
                    // DevTools will display the raw source and our explicit
                    // column numbers will work.
                    const script = document.createElement('script');
                    script.textContent = `${content}\n//# sourceURL=${virtualUrl}`;

                    // HACK: Suppress syntax errors from Python code being parsed as JS
                    // We want the script to be loaded for DevTools, but not to clutter console.
                    const handler = (e: ErrorEvent) => {
                        if (e.target === window || e.target === script) {
                            e.preventDefault();
                            e.stopImmediatePropagation();
                        }
                    };
                    window.addEventListener('error', handler, true); // Capture phase
                    try {
                        document.head.appendChild(script);
                    } finally {
                        // Remove handler immediately after synchronous execution attempt
                        window.removeEventListener('error', handler, true);
                    }

                    this.loadedSources.add(filename);
                }

                this.loadedSources.add(filename);
            } catch (e) {
                console.warn('PyHTML: Failed to load source', filename, e);
            }
        }));

        // Construct Error with stack pointing to absolute virtual URLs
        const err = new Error(errorMessage);
        const stackLines = [`${err.name}: ${err.message}`];

        for (const frame of trace) {
            const fn = frame.name || '<module>';
            const virtualUrl = this.getVirtualUrl(frame.filename);
            // Format: at functionName (url:line:col)
            // Use colno from Python 3.11+ if available, otherwise default to 1
            const col = frame.colno ?? 1;
            stackLines.push(`    at ${fn} (${virtualUrl}:${frame.lineno}:${col})`);
        }

        err.stack = stackLines.join('\n');

        // Log just the stack string to avoid Chrome appending its own call stack
        console.error(err.stack);
    }

    /**
     * Handle incoming server message.
     */
    private async handleMessage(msg: ServerMessage): Promise<void> {
        switch (msg.type) {
            case 'update':
                if (msg.html) {
                    this.updater.update(msg.html);
                }
                break;

            case 'reload':
                console.log('PyHTML: Reloading...');
                window.location.reload();
                break;

            case 'error':
                console.error('PyHTML: Server error:', msg.error);
                break;

            case 'error_trace':
                if (msg.trace) {
                    await this.handleErrorTrace(msg.error || 'Unknown Error', msg.trace);
                }
                break;

            case 'console':
                if (msg.lines && msg.lines.length > 0) {
                    const prefix = 'PyHTML Server:';
                    const joined = msg.lines.join('\n');
                    if (msg.level === 'error') {
                        console.group(prefix + ' Error');
                        console.error(joined);
                        console.groupEnd();
                    } else if (msg.level === 'warn') {
                        console.groupCollapsed(prefix + ' Warning');
                        console.warn(joined);
                        console.groupEnd();
                    } else {
                        if (msg.lines.length === 1) {
                            console.log(prefix, joined);
                        } else {
                            console.groupCollapsed(prefix + ' Log');
                            console.log(joined);
                            console.groupEnd();
                        }
                    }
                }
                break;

            default:
                console.warn('PyHTML: Unknown message type', msg);
        }
    }

    /**
     * Get the current transport name.
     */
    getTransport(): string | null {
        return this.transport.getActiveTransport();
    }

    /**
     * Disconnect from the server.
     */
    disconnect(): void {
        this.transport.disconnect();
    }
}

// Auto-initialize
const app = new PyHTMLApp();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}

// Export for external use
export { app };
export { TransportManager } from './transport-manager';
export { DOMUpdater } from './dom-updater';
export * from './transports';
