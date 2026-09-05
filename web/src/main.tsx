/** Console entry point.
 *
 * Provider order matters: Query before Live, because `LiveProvider` reads the session
 * store and mounts the socket for whichever experiment id is current, and a screen may
 * both stream and fetch. Router outermost so a crash inside a screen can still be
 * navigated away from.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { ApiError } from "@/api/client";
import { App } from "@/App";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { LiveProvider } from "@/state/LiveProvider";

import "@/styles/index.css";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      // A 503 means the spectrum cache or the window index has not been built. Retrying
      // cannot fix that — only `make data` / `make index` can — so surface it at once
      // instead of spending four round trips pretending it might resolve itself.
      retry: (attempt, error) => !(error instanceof ApiError) && attempt < 2,
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <LiveProvider>
          <ErrorBoundary where="The console">
            <App />
          </ErrorBoundary>
        </LiveProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
