/**
 * Base transport interface for all transport implementations.
 */
export interface Transport {
    /** Connect to the server */
    connect(): Promise<void>;

    /** Send a message to the server */
    send(message: object): void;

    /** Register a message handler */
    onMessage(handler: MessageHandler): void;

    /** Disconnect from the server */
    disconnect(): void;

    /** Check if connected */
    isConnected(): boolean;

    /** Transport name for debugging */
    readonly name: string;
}

export type MessageHandler = (message: ServerMessage) => void;

export interface ServerMessage {
    type: 'update' | 'reload' | 'error';
    html?: string;
    error?: string;
}

export interface ClientMessage {
    type: 'event';
    handler: string;
    path: string;
    data: EventData;
}

export interface EventData {
    type: string;
    id?: string;
    value?: string;
    [key: string]: unknown;
}

/**
 * Abstract base class providing common transport functionality.
 */
export abstract class BaseTransport implements Transport {
    protected messageHandlers: MessageHandler[] = [];
    protected connected = false;

    abstract readonly name: string;
    abstract connect(): Promise<void>;
    abstract send(message: object): void;
    abstract disconnect(): void;

    onMessage(handler: MessageHandler): void {
        this.messageHandlers.push(handler);
    }

    isConnected(): boolean {
        return this.connected;
    }

    protected notifyHandlers(message: ServerMessage): void {
        for (const handler of this.messageHandlers) {
            try {
                handler(message);
            } catch (e) {
                console.error('PyHTML: Error in message handler', e);
            }
        }
    }
}
