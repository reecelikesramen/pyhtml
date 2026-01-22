import { TransportManager, TransportConfig } from './transport-manager';
import { DOMUpdater } from './dom-updater';
import { ServerMessage, ClientMessage, EventData, RelocateMessage } from './transports';
import { UnifiedEventHandler } from './events/handler';

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
    private eventHandler: UnifiedEventHandler;
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
        this.eventHandler = new UnifiedEventHandler(this);
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
        this.eventHandler.init();

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

        // Handle browser back/forward
        window.addEventListener('popstate', () => {
            this.sendRelocate(window.location.pathname + window.location.search);
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
