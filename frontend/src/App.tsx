import { useState } from "react";
import { ApiError, rankStores, type RankRequest, type RankResponse } from "./api/client";
import { RankForm } from "./components/RankForm";
import { Results } from "./components/Results";

/**
 * Where the page is, as one value rather than separate `loading`, `error` and
 * `response` flags: a union can't be "loading" and "error" at the same time.
 */
type RankState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; response: RankResponse; cuisinesChosen: boolean }
  | { status: "failed"; message: string };

export function App() {
  const [state, setState] = useState<RankState>({ status: "idle" });

  async function rank(request: RankRequest) {
    setState({ status: "loading" });
    try {
      const response = await rankStores(request);
      setState({ status: "done", response, cuisinesChosen: Boolean(request.cuisines?.length) });
    } catch (error) {
      if (!(error instanceof ApiError)) {
        console.error(error);
      }
      const message = error instanceof ApiError ? error.message : "Something went wrong.";
      setState({ status: "failed", message });
    }
  }

  return (
    <main className="page">
      <header className="masthead">
        <h1>
          <span aria-hidden="true">🧭</span> Koopjeskompas
        </h1>
        <p className="tagline">Which nearby supermarket has the best deals for you this week?</p>
      </header>

      <RankForm busy={state.status === "loading"} onSubmit={(request) => void rank(request)} />

      {state.status === "failed" && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.status === "done" && (
        <Results response={state.response} cuisinesChosen={state.cuisinesChosen} />
      )}
    </main>
  );
}
