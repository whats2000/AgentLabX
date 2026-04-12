import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Import is deferred into each test via dynamic import so vi.resetModules() gives
// each test a fresh singleton (otherwise the first test pollutes the registry).

describe("wsRegistry", () => {
  let connectMock: ReturnType<typeof vi.fn>;
  let disconnectMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    connectMock = vi.fn();
    disconnectMock = vi.fn();
    // Mock SessionWebSocket — the registry should only call connect/disconnect
    vi.doMock("../../src/api/ws", () => ({
      SessionWebSocket: vi.fn().mockImplementation((sessionId: string) => ({
        sessionId,
        connect: connectMock,
        disconnect: disconnectMock,
        onEvent: vi.fn().mockReturnValue(() => undefined),
      })),
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.doUnmock("../../src/api/ws");
  });

  it("two acquires for same session share one socket", async () => {
    const { wsRegistry } = await import("../../src/api/wsRegistry");
    const a = wsRegistry.acquire("sess-1");
    const b = wsRegistry.acquire("sess-1");
    expect(a).toBe(b);
    expect(connectMock).toHaveBeenCalledTimes(1);
  });

  it("acquire + release within debounce window keeps socket alive", async () => {
    const { wsRegistry } = await import("../../src/api/wsRegistry");
    wsRegistry.acquire("sess-1");
    wsRegistry.release("sess-1");
    // Advance less than the debounce window
    vi.advanceTimersByTime(25);
    wsRegistry.acquire("sess-1");
    // Fire any remaining timers — none should close the socket
    vi.advanceTimersByTime(100);
    expect(disconnectMock).not.toHaveBeenCalled();
  });

  it("acquire + release with no re-acquire disconnects after debounce", async () => {
    const { wsRegistry } = await import("../../src/api/wsRegistry");
    wsRegistry.acquire("sess-1");
    wsRegistry.release("sess-1");
    // Before debounce fires, socket is still alive
    vi.advanceTimersByTime(40);
    expect(disconnectMock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(20); // now past 50ms
    expect(disconnectMock).toHaveBeenCalledTimes(1);
  });

  it("StrictMode-style release then re-acquire keeps socket (1->0->1)", async () => {
    const { wsRegistry } = await import("../../src/api/wsRegistry");
    // Simulate: mount -> effect -> cleanup -> effect
    wsRegistry.acquire("sess-1"); // refcount 1
    wsRegistry.release("sess-1"); // refcount 0, teardown scheduled
    wsRegistry.acquire("sess-1"); // refcount 1, teardown cancelled
    vi.advanceTimersByTime(200);
    expect(disconnectMock).not.toHaveBeenCalled();
    expect(connectMock).toHaveBeenCalledTimes(1);
  });

  it("double release never goes negative", async () => {
    const { wsRegistry } = await import("../../src/api/wsRegistry");
    wsRegistry.acquire("sess-1");
    wsRegistry.release("sess-1");
    wsRegistry.release("sess-1"); // extra release
    vi.advanceTimersByTime(200);
    // Socket should still disconnect at most once — no throw on extra release
    expect(disconnectMock).toHaveBeenCalledTimes(1);
  });

  it("release for unknown session is a no-op", async () => {
    const { wsRegistry } = await import("../../src/api/wsRegistry");
    expect(() => wsRegistry.release("unknown")).not.toThrow();
  });
});
