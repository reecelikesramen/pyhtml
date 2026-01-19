import { BaseTransport, ServerMessage } from './base';

/**
 * WebTransport implementation using the browser's native WebTransport API.
 * WebTransport provides lower latency than WebSocket via HTTP/3 and QUIC.
 */
export class WebTransportTransport extends BaseTransport {
    readonly name = 'WebTransport';

    private transport: WebTransport | null = null;
    private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
    private readonly url: string;
    private encoder = new TextEncoder();
    private decoder = new TextDecoder();
    private shouldReconnect = true;
    private reconnectAttempts = 0;
    private maxReconnectDelay = 5000;

    constructor(url?: string) {
        super();
        this.url = url || this.getDefaultUrl();
    }

    private getDefaultUrl(): string {
        // WebTransport requires HTTPS
        return `https://${window.location.host}/_pyhtml/webtransport`;
    }

    /**
     * Check if WebTransport is available in this browser.
     */
    static isSupported(): boolean {
        return typeof WebTransport !== 'undefined';
    }

    async connect(): Promise<void> {
        if (!WebTransportTransport.isSupported()) {
            throw new Error('WebTransport not supported in this browser');
        }

        try {
            // Check for self-signed cert hash (Dev Mode)
            const options: WebTransportOptions = {};
            const certHash = (window as any).PYHTML_CERT_HASH;
            if (certHash && Array.isArray(certHash)) {
                options.serverCertificateHashes = [{
                    algorithm: 'sha-256',
                    value: new Uint8Array(certHash)
                }];
                console.log("PyHTML: Using explicit certificate hash for WebTransport");
            }

            this.transport = new WebTransport(this.url, options);

            // Wait for the connection to be ready
            await this.transport.ready;

            console.log('PyHTML: WebTransport ready');
            this.connected = true;
            this.reconnectAttempts = 0;

            // Send init message for page instantiation
            await this.sendInit();

            // Start reading incoming streams
            this.startReading();

            // Handle connection close
            this.transport.closed.then(() => {
                console.log('PyHTML: WebTransport closed');
                this.handleDisconnect();
                if (this.shouldReconnect) {
                    this.scheduleReconnect();
                }
            }).catch((e) => {
                console.error('PyHTML: WebTransport closed with error', e);
                this.handleDisconnect();
                if (this.shouldReconnect) {
                    this.scheduleReconnect();
                }
            });

        } catch (e) {
            this.handleDisconnect();
            throw e;
        }
    }

    /**
     * Send init message to initialize page on server.
     */
    private async sendInit(): Promise<void> {
        await this.send({
            type: 'init',
            path: window.location.pathname + window.location.search
        });
    }

    private async startReading(): Promise<void> {
        if (!this.transport) return;

        // Read from bidirectional streams (responses to our requests)
        this.readBidirectionalStreams();

        // Read from datagrams (server-initiated messages like broadcast_reload)
        this.readDatagrams();
    }

    private async readBidirectionalStreams(): Promise<void> {
        if (!this.transport) return;

        const reader = this.transport.incomingBidirectionalStreams.getReader();

        try {
            while (true) {
                const { value: stream, done } = await reader.read();
                if (done) break;

                // Handle each incoming stream
                this.handleStream(stream);
            }
        } catch (e) {
            if (this.connected) {
                console.error('PyHTML: WebTransport bidirectional stream read error', e);
            }
        }
    }

    private async readDatagrams(): Promise<void> {
        if (!this.transport) return;

        const reader = this.transport.datagrams.readable.getReader();

        try {
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                if (value) {
                    const text = this.decoder.decode(value);
                    try {
                        const msg = JSON.parse(text) as ServerMessage;
                        this.notifyHandlers(msg);
                    } catch (e) {
                        console.error('PyHTML: Error parsing WebTransport datagram', e);
                    }
                }
            }
        } catch (e) {
            if (this.connected) {
                console.error('PyHTML: WebTransport datagram read error', e);
            }
        }
    }

    private async handleStream(stream: WebTransportBidirectionalStream): Promise<void> {
        const reader = stream.readable.getReader();
        let buffer = '';

        try {
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                if (value) {
                    buffer += this.decoder.decode(value, { stream: true });
                }
            }

            // Parse complete message
            if (buffer) {
                try {
                    const msg = JSON.parse(buffer) as ServerMessage;
                    this.notifyHandlers(msg);
                } catch (e) {
                    console.error('PyHTML: Error parsing WebTransport message', e, buffer);
                }
            }
        } catch (e) {
            console.error('PyHTML: Stream read error', e);
        }
    }

    async send(message: object): Promise<void> {
        if (!this.transport || !this.connected) {
            console.warn('PyHTML: Cannot send message, WebTransport not connected');
            return;
        }

        try {
            // Create a new bidirectional stream for each message
            const stream = await this.transport.createBidirectionalStream();
            const writer = stream.writable.getWriter();

            const data = this.encoder.encode(JSON.stringify(message));
            await writer.write(data);
            await writer.close();

            // Read the response from this stream
            this.handleStream(stream);

        } catch (e) {
            console.error('PyHTML: WebTransport send error', e);
        }
    }

    disconnect(): void {
        this.shouldReconnect = false;
        if (this.transport) {
            this.transport.close();
            this.transport = null;
        }
        this.writer = null;
        this.connected = false;
    }

    private handleDisconnect(): void {
        this.connected = false;
        this.transport = null;
        this.writer = null;
    }

    private scheduleReconnect(): void {
        const delay = Math.min(
            1000 * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );

        console.log(`PyHTML: WebTransport reconnecting in ${delay}ms...`);

        setTimeout(() => {
            this.reconnectAttempts++;
            this.connect().catch((e) => {
                console.warn('PyHTML: WebTransport reconnect failed', e);
                // Will try again via closed handler
            });
        }, delay);
    }
}
