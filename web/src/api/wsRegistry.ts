import { SessionWebSocket } from "./ws";

// ~50ms absorbs React 19 StrictMode's dev-only mount -> cleanup -> mount cycle
// without affecting production teardown behaviour. The second acquire cancels
// the pending teardown timer before the socket actually closes.
const TEARDOWN_DEBOUNCE_MS = 50;

interface Entry {
  socket: SessionWebSocket;
  refcount: number;
  teardownTimer: ReturnType<typeof setTimeout> | null;
}

/**
 * Registry of session_id -> shared SessionWebSocket. Fix D: the debounced
 * teardown ensures that React 19 StrictMode's double-invoke of effects
 * (mount -> cleanup -> mount) does not churn the underlying socket.
 */
class WebSocketRegistry {
  private entries = new Map<string, Entry>();

  acquire(sessionId: string): SessionWebSocket {
    let entry = this.entries.get(sessionId);
    if (!entry) {
      const socket = new SessionWebSocket(sessionId);
      socket.connect();
      entry = { socket, refcount: 0, teardownTimer: null };
      this.entries.set(sessionId, entry);
    }
    if (entry.teardownTimer !== null) {
      clearTimeout(entry.teardownTimer);
      entry.teardownTimer = null;
    }
    entry.refcount += 1;
    return entry.socket;
  }

  release(sessionId: string): void {
    const entry = this.entries.get(sessionId);
    if (!entry) return;
    entry.refcount -= 1;
    if (entry.refcount <= 0) {
      if (entry.teardownTimer !== null) {
        clearTimeout(entry.teardownTimer);
      }
      entry.teardownTimer = setTimeout(() => {
        const current = this.entries.get(sessionId);
        if (!current || current.refcount > 0) return;
        current.socket.disconnect();
        this.entries.delete(sessionId);
      }, TEARDOWN_DEBOUNCE_MS);
    }
  }
}

export const wsRegistry = new WebSocketRegistry();
