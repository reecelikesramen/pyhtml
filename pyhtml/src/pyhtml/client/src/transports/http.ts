import { BaseTransport, ServerMessage } from './base';

/**
 * HTTP polling transport as a fallback when WebTransport and WebSocket are unavailable.
 * Uses long-polling for receiving updates and POST for sending events.
 */
export class HTTPTransport extends BaseTransport {
    readonly name = 'HTTP';

    private polling = false;
    private pollAbortController: AbortController | null = null;
    private readonly baseUrl: string;
    private sessionId: string | null = null;

    constructor(baseUrl?: string) {
        super();
        this.baseUrl = baseUrl || `${window.location.origin}/_pyhtml`;
    }

    async connect(): Promise<void> {
        try {
            // Initialize session with the server
            const response = await fetch(`${this.baseUrl}/session`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: window.location.pathname + window.location.search })  // Include query string
            });

            if (!response.ok) {
                throw new Error(`HTTP session init failed: ${response.status}`);
            }

            const data = await response.json();
            this.sessionId = data.sessionId;

            console.log('PyHTML: HTTP transport connected');
            this.connected = true;

            // Start polling for updates
            this.startPolling();

        } catch (e) {
            console.error('PyHTML: HTTP transport connection failed', e);
            throw e;
        }
    }

    private async startPolling(): Promise<void> {
        if (this.polling) return;
        this.polling = true;

        while (this.polling && this.connected) {
            try {
                this.pollAbortController = new AbortController();

                const response = await fetch(`${this.baseUrl}/poll?session=${this.sessionId}`, {
                    method: 'GET',
                    signal: this.pollAbortController.signal,
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    if (response.status === 404) {
                        // Session expired, try to reconnect
                        console.warn('PyHTML: HTTP session expired, reconnecting...');
                        this.connected = false;
                        await this.connect();
                        return;
                    }
                    throw new Error(`Poll failed: ${response.status}`);
                }

                const messages = await response.json() as ServerMessage[];

                for (const msg of messages) {
                    this.notifyHandlers(msg);
                }

            } catch (e) {
                if (e instanceof Error && e.name === 'AbortError') {
                    // Polling was aborted intentionally
                    break;
                }
                console.error('PyHTML: HTTP poll error', e);
                // Wait a bit before retrying
                await this.sleep(1000);
            }
        }
    }

    async send(message: object): Promise<void> {
        if (!this.connected || !this.sessionId) {
            console.warn('PyHTML: Cannot send message, HTTP transport not connected');
            return;
        }

        try {
            const response = await fetch(`${this.baseUrl}/event`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-PyHTML-Session': this.sessionId
                },
                body: JSON.stringify(message)
            });

            if (!response.ok) {
                throw new Error(`Event send failed: ${response.status}`);
            }

            // The response contains the updated HTML
            const result = await response.json() as ServerMessage;
            this.notifyHandlers(result);

        } catch (e) {
            console.error('PyHTML: HTTP send error', e);
        }
    }

    disconnect(): void {
        this.polling = false;
        this.connected = false;

        if (this.pollAbortController) {
            this.pollAbortController.abort();
            this.pollAbortController = null;
        }

        this.sessionId = null;
    }

    private sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}
