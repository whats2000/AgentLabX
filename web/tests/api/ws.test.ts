import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionWebSocket } from "../../src/api/ws";

class MockWebSocket {
  static OPEN = 1;
  readyState: number = MockWebSocket.OPEN;
  handlers: Record<string, ((ev: unknown) => void)[]> = {};
  sent: string[] = [];
  addEventListener(type: string, handler: (ev: unknown) => void) {
    (this.handlers[type] ??= []).push(handler);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.handlers["close"]?.forEach((h) => h({ code: 1000 }));
  }
  trigger(type: string, event: unknown) {
    this.handlers[type]?.forEach((h) => h(event));
  }
}

describe("SessionWebSocket", () => {
  let instances: MockWebSocket[] = [];
  let ctor: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    instances = [];
    ctor = vi.fn().mockImplementation(() => {
      const instance = new MockWebSocket();
      instances.push(instance);
      return instance;
    });
    vi.stubGlobal("WebSocket", ctor);
    Object.defineProperty(WebSocket, "OPEN", {
      value: 1,
      configurable: true,
    });
    Object.defineProperty(window, "location", {
      value: { host: "localhost:5173", protocol: "http:" },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("delivers events to subscribers", () => {
    const ws = new SessionWebSocket("sess-1");
    const handler = vi.fn();
    ws.onEvent(handler);
    ws.connect();
    instances[0].trigger("message", {
      data: JSON.stringify({ type: "stage_started", data: { stage: "x" } }),
    });
    expect(handler).toHaveBeenCalledWith({
      type: "stage_started",
      data: { stage: "x" },
    });
  });

  it("sends actions as JSON when socket is OPEN", () => {
    const ws = new SessionWebSocket("sess-1");
    ws.connect();
    ws.send({ action: "update_preferences", mode: "hitl" });
    expect(instances[0].sent[0]).toBe(
      JSON.stringify({ action: "update_preferences", mode: "hitl" }),
    );
  });

  it("drops actions when socket not open", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const ws = new SessionWebSocket("sess-1");
    ws.connect();
    instances[0].readyState = 0; // CONNECTING
    ws.send({ action: "approve" });
    expect(instances[0].sent).toHaveLength(0);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("unsubscribes handlers", () => {
    const ws = new SessionWebSocket("sess-1");
    const handler = vi.fn();
    const unsubscribe = ws.onEvent(handler);
    ws.connect();
    unsubscribe();
    instances[0].trigger("message", {
      data: JSON.stringify({ type: "stage_started", data: {} }),
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("does not reconnect after disconnect()", () => {
    const ws = new SessionWebSocket("sess-1");
    ws.connect();
    ws.disconnect();
    // triggering close on the now-detached socket must not recreate
    instances[0].trigger("close", { code: 1000 });
    expect(ctor).toHaveBeenCalledTimes(1);
  });

  it("logs on unparseable messages", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const ws = new SessionWebSocket("sess-1");
    ws.connect();
    instances[0].trigger("message", { data: "not json" });
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("drops non-string frames with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const handler = vi.fn();
    const ws = new SessionWebSocket("sess-1");
    ws.onEvent(handler);
    ws.connect();
    instances[0].trigger("message", { data: new ArrayBuffer(4) });
    expect(handler).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("isolates throwing subscribers so peers still run", () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const throwing = vi.fn(() => {
      throw new Error("boom");
    });
    const peer = vi.fn();
    const ws = new SessionWebSocket("sess-1");
    ws.onEvent(throwing);
    ws.onEvent(peer);
    ws.connect();
    instances[0].trigger("message", {
      data: JSON.stringify({ type: "stage_started", data: {} }),
    });
    expect(throwing).toHaveBeenCalledTimes(1);
    expect(peer).toHaveBeenCalledTimes(1);
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });

  it("exposes sessionId and url for debugging", () => {
    const ws = new SessionWebSocket("sess-42");
    expect(ws.sessionId).toBe("sess-42");
    expect(ws.url).toContain("/ws/sessions/sess-42");
  });
});
