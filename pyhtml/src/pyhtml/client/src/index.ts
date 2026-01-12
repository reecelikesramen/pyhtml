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
 * Main PyHTML Application class.
 */
export class PyHTMLApp {
    private transport: TransportManager;
    private updater: DOMUpdater;
    private initialized = false;
    private config: PyHTMLConfig;
    private siblingPaths: string[] = [];
    private pathRegexes: RegExp[] = [];

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

        console.log(`PyHTML: Initialized (transport: ${this.transport.getActiveTransport()}, spa_paths: ${this.siblingPaths.length})`);
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
        if (this.siblingPaths.length === 0) return;

        // Intercept link clicks
        document.addEventListener('click', (e) => {
            const link = (e.target as Element).closest('a[href]') as HTMLAnchorElement | null;
            if (!link) return;

            // Only intercept same-origin links
            if (link.origin !== window.location.origin) return;

            // Check if the path matches a sibling path
            if (this.isSiblingPath(link.pathname)) {
                e.preventDefault();
                this.navigateTo(link.pathname + link.search);
            }
        });

        // Handle browser back/forward
        window.addEventListener('popstate', () => {
            this.sendRelocate(window.location.pathname + window.location.search);
        });
    }

    /**
     * Navigate to a sibling path using SPA navigation.
     */
    navigateTo(path: string): void {
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
        document.addEventListener('submit', (e) => {
            const target = (e.target as Element).closest('[data-on-submit]');
            if (target) {
                e.preventDefault();
                const handler = target.getAttribute('data-on-submit');
                if (handler) {
                    // Collect form data
                    const formData = new FormData(target as HTMLFormElement);
                    const data: Record<string, string> = {};
                    formData.forEach((value, key) => {
                        data[key] = value.toString();
                    });

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
    private handleMessage(msg: ServerMessage): void {
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

            case 'console':
                if (msg.lines) {
                    const prefix = 'PyHTML Server:';
                    const lines = msg.lines;
                    if (msg.level === 'error') {
                        console.error(prefix, ...lines);
                    } else if (msg.level === 'warn') {
                        console.warn(prefix, ...lines);
                    } else {
                        console.log(prefix, ...lines);
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
