import "@ant-design/v5-patch-for-react-19";
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// Reset the module-scope turn→agent map between tests to prevent cross-test
// pollution that causes flaky failures when the full suite runs.
afterEach(async () => {
  const mod = await import("../src/hooks/useWebSocket");
  mod._clearAllTurnMaps();
});

// jsdom doesn't implement matchMedia; AntD's responsive grid/table observers
// call it on mount. Provide a minimal MediaQueryList stub so Table renders.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
