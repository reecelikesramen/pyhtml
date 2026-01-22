import { TransportManager, TransportConfig } from './transport-manager';
import { DOMUpdater } from './dom-updater';
import { ServerMessage, ClientMessage, EventData, RelocateMessage } from './transports';

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
 * Core PyHTML Application class.
 * Provides transport, DOM updates, SPA navigation, and event handling.
 * Dev-only features (status overlay, error traces) are in the dev bundle.
 */
export class PyHTMLApp {
    protected transport: TransportManager;
    protected updater: DOMUpdater;
    protected initialized = false;
    protected config: PyHTMLConfig;
    protected siblingPaths: string[] = [];
    protected pathRegexes: RegExp[] = [];
    protected pjaxEnabled = false;
    protected isConnected = false;

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
     * Handle connection status changes. Override in dev bundle for UI.
     */
    protected handleStatusChange(connected: boolean): void {
        this.isConnected = connected;
        // Base implementation: no UI, just track state
    }

    /**
     * Load SPA navigation metadata from injected script tag.
     */
    protected loadSPAMetadata(): void {
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

    /**
     * Convert route pattern like '/a/:id' to regex.
     */
    protected patternToRegex(pattern: string): RegExp {
        // Escape special regex chars except for our placeholders
        let regex = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
        // Replace :param:type or :param with capture groups
        regex = regex.replace(/:(\\w+)(:\\w+)?/g, '([^/]+)');
        // Replace {param:type} or {param} with capture groups
        regex = regex.replace(/\\{(\\w+)(:\\w+)?\\}/g, '([^/]+)');
        return new RegExp(`^${regex}$`);
    }

    /**
     * Check if a path matches any sibling path pattern.
     */
    protected isSiblingPath(path: string): boolean {
        return this.pathRegexes.some(regex => regex.test(path));
    }

    /**
     * Setup SPA navigation for sibling paths.
     */
    protected setupSPANavigation(): void {
        // Handle browser back/forward
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
                shouldIntercept = true;
            } else if (this.isSiblingPath(link.pathname)) {
                shouldIntercept = true;
            }

            if (shouldIntercept) {
                e.preventDefault();
                this.navigateTo(link.pathname + link.search);
            }
        });
    }

    /**
     * Navigate to a path using SPA navigation.
     */
    navigateTo(path: string): void {
        if (!this.isConnected) {
            console.warn('PyHTML: Navigation blocked - Offline');
            return;
        }

        history.pushState({}, '', path);
        this.sendRelocate(path);
    }

    /**
     * Send relocate message to server.
     */
    protected sendRelocate(path: string): void {
        const message: RelocateMessage = {
            type: 'relocate',
            path
        };
        this.transport.send(message);
    }

    /**
     * Setup DOM event interceptors.
     */
    protected setupEventInterceptors(): void {
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
                    const formData = new FormData(form);
                    const data: Record<string, any> = {};

                    // Handle regular fields
                    formData.forEach((value, key) => {
                        if (!(value instanceof File)) {
                            data[key] = value.toString();
                        }
                    });

                    // Handle file uploads
                    const fileInputs = form.querySelectorAll('input[type="file"]');
                    const uploadPromises: Promise<void>[] = [];

                    fileInputs.forEach((input) => {
                        const fileInput = input as HTMLInputElement;
                        const name = fileInput.name;
                        if (!name) return;

                        if (fileInput.files && fileInput.files.length > 0) {
                            const file = fileInput.files[0];

                            // Client-side size validation
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
                                let lastProgressTime = 0;
                                xhr.upload.onprogress = (ev) => {
                                    if (ev.lengthComputable) {
                                        const now = Date.now();
                                        if (now - lastProgressTime >= 100) {
                                            lastProgressTime = now;
                                            const percent = ev.loaded / ev.total;

                                            const progressHandler = fileInput.getAttribute('data-on-upload-progress');
                                            if (progressHandler) {
                                                this.sendEvent(progressHandler, {
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
                                                reject(new Error('No ID returned'));
                                            }
                                        } catch (err) {
                                            reject(err);
                                        }
                                    } else {
                                        const msg = `Upload failed: ${xhr.status} ${xhr.statusText}`;
                                        alert(msg);
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
                    try {
                        await Promise.all(uploadPromises);
                    } catch (err) {
                        console.error('PyHTML: Upload failed', err);
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

        // Input events (debounced)
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
                }, 150);
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
    protected getArgs(element: Element): Record<string, unknown> {
        const args: Record<string, unknown> = {};
        if (element instanceof HTMLElement) {
            for (const key in element.dataset) {
                if (key.startsWith('arg')) {
                    try {
                        args[key] = JSON.parse(element.dataset[key] || 'null');
                    } catch {
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
     * Handle incoming server message. Override in dev bundle for error_trace.
     */
    protected async handleMessage(msg: ServerMessage): Promise<void> {
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
                // In core bundle, just log the error (no source loading)
                console.error('PyHTML: Error:', msg.error);
                break;

            case 'console':
                if (msg.lines && msg.lines.length > 0) {
                    const prefix = 'PyHTML Server:';
                    const joined = msg.lines.join('\n');
                    if (msg.level === 'error') {
                        console.error(prefix, joined);
                    } else if (msg.level === 'warn') {
                        console.warn(prefix, joined);
                    } else {
                        console.log(prefix, joined);
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
