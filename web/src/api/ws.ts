import type { PipelineEvent, ClientAction } from "../types/events";

export type EventHandler = (event: PipelineEvent) => void;

function wsScheme(): string {
  return window.location.protocol === "https:" ? "wss" : "ws";
}

/**
 * Thin wrapper around a browser WebSocket keyed by session_id.
 * Knows nothing about React or the registry — suitable for unit testing
 * in isolation. The registry layer (wsRegistry.ts) handles sharing a
 * single instance across components.
 */
export class SessionWebSocket {
  private socket: WebSocket | null = null;
  private handlers = new Set<EventHandler>();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manuallyClosed = false;

  constructor(
    sessionId: string,
    private readonly url: string = `${wsScheme()}://${window.location.host}/ws/sessions/${sessionId}`,
  ) {
    // sessionId is only used to derive the default URL above; we do not need
    // to retain it as a class property.
    void sessionId;
  }

  connect(): void {
    this.manuallyClosed = false;
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener("open", () => {
      this.reconnectAttempts = 0;
    });
    this.socket.addEventListener("message", (ev) => {
      try {
        const payload = JSON.parse(
          (ev as MessageEvent).data as string,
        ) as PipelineEvent;
        this.handlers.forEach((h) => h(payload));
      } catch (err) {
        console.warn("Failed to parse WS message:", err);
      }
    });
    this.socket.addEventListener("close", () => {
      if (this.manuallyClosed) return;
      const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
      this.reconnectAttempts += 1;
      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    });
  }

  disconnect(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }

  send(action: ClientAction): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(action));
    } else {
      console.warn("WS not open, dropping action:", action);
    }
  }

  onEvent(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }
}
