import { useState } from "react";
import { ApiError, rankStores, type RankRequest, type RankResponse } from "../api/client";
import { RankForm } from "../components/RankForm";
import { Results } from "../components/Results";

/**
 * Where the page is, as one value rather than separate `loading`, `error` and
 * `response` flags: a union can't be "loading" and "error" at the same time.
 */
type RankState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; response: RankResponse; cuisinesChosen: boolean }
  | { status: "failed"; message: string };

/** The supermarkets: your location and preferences in, ranked stores out. */
export function RankPage() {
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
    <>
      <p className="tagline">Which nearby supermarket has the best deals for you this week?</p>

      <RankForm busy={state.status === "loading"} onSubmit={(request) => void rank(request)} />

      {state.status === "failed" && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.status === "done" && (
        <Results response={state.response} cuisinesChosen={state.cuisinesChosen} />
      )}

      <footer className="sources">
        <p>
          Stores © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors.
          Place search by{" "}
          <a href="https://www.pdok.nl/introductie/-/article/pdok-locatieserver-1">
            PDOK Locatieserver
          </a>
          : what you type there is sent to PDOK, the Dutch government&rsquo;s map service.
        </p>
      </footer>
    </>
  );
}
