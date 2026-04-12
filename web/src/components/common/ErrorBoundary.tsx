import { Component, type ErrorInfo, type ReactNode } from "react";
import { Result, Button } from "antd";

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Route error:", error, info);
  }

  handleRetry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title={this.props.fallbackLabel ?? "Something went wrong"}
          subTitle={this.state.error.message}
          extra={
            <Button type="primary" onClick={this.handleRetry}>
              Retry
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
