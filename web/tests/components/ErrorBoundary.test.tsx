import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { ReactElement } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBoundary } from "../../src/components/common/ErrorBoundary";

function Boom({ message = "boom" }: { message?: string }): never {
  throw new Error(message);
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>safe</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("safe")).toBeInTheDocument();
  });

  it("catches a child error and shows the Result fallback", () => {
    render(
      <ErrorBoundary>
        <Boom message="kaboom" />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/kaboom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("honors custom fallbackLabel", () => {
    render(
      <ErrorBoundary fallbackLabel="Dashboard failed">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Dashboard failed")).toBeInTheDocument();
  });

  it("Retry clears the error and re-renders children", () => {
    let shouldThrow = true;
    function Maybe(): ReactElement {
      if (shouldThrow) throw new Error("one time");
      return <p>recovered</p>;
    }
    render(
      <ErrorBoundary>
        <Maybe />
      </ErrorBoundary>,
    );
    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(screen.getByText("recovered")).toBeInTheDocument();
  });
});
