import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Keeps a single malformed payload from blanking the whole workspace.
 *
 * The workspace renders data from six endpoints; one unexpected shape used to
 * take the entire application down with a white screen, which is the worst
 * possible failure during a demo or an incident review.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept on the console rather than shipped anywhere: this app has no client
    // telemetry endpoint, and inventing one silently would be worse than logging.
    console.error('CaseGraph workspace error', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <main>
          <header className="topbar">
            <div className="brand">
              <b>CaseGraph</b>
              <span>workspace error</span>
            </div>
          </header>
          <div className="alert danger" role="alert">
            The workspace hit an unexpected error and stopped rendering. Nothing was executed and no PayPal
            action was taken from this screen.
          </div>
          <div className="card" style={{ margin: '16px 26px' }}>
            <h3>Details</h3>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{this.state.error.message}</pre>
            <button type="button" style={{ marginTop: 12 }} onClick={() => window.location.reload()}>
              Reload workspace
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
