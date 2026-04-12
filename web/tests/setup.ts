import "@ant-design/v5-patch-for-react-19";
import "@testing-library/jest-dom/vitest";

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
