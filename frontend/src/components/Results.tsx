import type { RankResponse } from "../api/client";
import { formatDate } from "../format";
import { StoreCard } from "./StoreCard";

interface ResultsProps {
  response: RankResponse;
  /** Whether the request named cuisines, so deals can show that they fit them. */
  cuisinesChosen: boolean;
}

export function Results({ response, cuisinesChosen }: ResultsProps) {
  if (response.stores.length === 0) {
    return <p className="empty">No Albert Heijn within this distance. Try a larger radius.</p>;
  }
  return (
    <section className="results" aria-labelledby="results-heading">
      <h2 id="results-heading">Best stores for you</h2>
      <p className="hint">
        Albert Heijn bonus deals on {formatDate(response.ranked_on)}. Every AH has the same deals,
        so for now the nearest store wins.
        {cuisinesChosen && " Deals that fit your cuisines count for more, so they come first."}
      </p>
      <ol className="stores">
        {response.stores.map((ranked) => (
          <StoreCard
            key={`${ranked.store.chain} ${ranked.store.name}`}
            ranked={ranked}
            cuisinesChosen={cuisinesChosen}
          />
        ))}
      </ol>
    </section>
  );
}
