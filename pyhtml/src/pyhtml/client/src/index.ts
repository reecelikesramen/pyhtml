import { TransportManager, TransportConfig } from './transport-manager';
import { DOMUpdater } from './dom-updater';
import { ServerMessage, ClientMessage, EventData } from './transports';

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

        // Setup event interception
        this.setupEventInterceptors();

        console.log(`PyHTML: Initialized (transport: ${this.transport.getActiveTransport()})`);
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
                        value: (target as HTMLInputElement).value
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
                        formData: data
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
                            value: (target as HTMLInputElement).value
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
                        checked: (target as HTMLInputElement).checked
                    });
                }
            }
        });
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
