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
  public readonly url: string;

  constructor(
    public readonly sessionId: string,
    url?: string,
  ) {
    this.url =
      url ?? `${wsScheme()}://${window.location.host}/ws/sessions/${sessionId}`;
  }

  connect(): void {
    this.manuallyClosed = false;
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener("open", () => {
      this.reconnectAttempts = 0;
    });
    this.socket.addEventListener("message", (ev) => {
      const raw = (ev as MessageEvent).data;
      if (typeof raw !== "string") {
        console.warn(
          `WS[${this.sessionId}] dropping non-string frame (${typeof raw})`,
        );
        return;
      }
      let payload: PipelineEvent;
      try {
        payload = JSON.parse(raw) as PipelineEvent;
      } catch (err) {
        console.warn(`WS[${this.sessionId}] failed to parse message:`, err);
        return;
      }
      // One buggy subscriber must not silence its peers (cache invalidation,
      // UI updates, cost ticker may each subscribe independently).
      this.handlers.forEach((handler) => {
        try {
          handler(payload);
        } catch (err) {
          console.error(`WS[${this.sessionId}] handler threw:`, err);
        }
      });
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
    // Reset backoff so a later reuse (not currently a registry path, but
    // the class contract says "reusable") starts fresh.
    this.reconnectAttempts = 0;
    this.socket?.close();
    this.socket = null;
  }

  send(action: ClientAction): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(action));
    } else {
      console.warn(`WS[${this.sessionId}] not open, dropping action:`, action);
    }
  }

  onEvent(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }
}
