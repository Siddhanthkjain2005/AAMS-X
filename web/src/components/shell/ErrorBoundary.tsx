/** Last line of defence.
 *
 * A render crash in one panel must not take down the console mid-demo, and it must not
 * be silent either: the message and component stack are shown, because a blank panel with
 * no explanation is the one failure mode that looks like a wrong measurement.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui";

interface Props {
  children: ReactNode;
  /** Shown in the heading so the operator knows which panel failed. */
  where?: string;
}

interface State {
  error: Error | null;
  stack: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, stack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ stack: info.componentStack ?? null });
    console.error("AAMS-X render error", error, info);
  }

  render(): ReactNode {
    const { error, stack } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="panel lit m-4 max-w-3xl p-5">
        <h2 className="text-sm font-semibold text-bad">
          {this.props.where ? `${this.props.where} failed to render` : "This view failed to render"}
        </h2>
        <p className="mono mt-2 text-xs leading-relaxed text-ink-dim">{error.message}</p>
        {stack ? (
          <pre className="mt-3 max-h-48 overflow-auto rounded border border-line bg-void p-3 text-[10px] leading-relaxed text-faint">
            {stack.trim()}
          </pre>
        ) : null}
        <div className="mt-4 flex gap-2">
          <Button onClick={() => this.setState({ error: null, stack: null })}>Try again</Button>
          <Button variant="ghost" onClick={() => window.location.reload()}>
            Reload console
          </Button>
        </div>
      </div>
    );
  }
}
