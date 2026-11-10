import type { ChainDeals, RankResponse } from "../api/client";
import { formatDate } from "../format";
import { StoreCard } from "./StoreCard";

interface ResultsProps {
  response: RankResponse;
  /** Whether the request named cuisines, so deals can show that they fit them. */
  cuisinesChosen: boolean;
}

export function Results({ response, cuisinesChosen }: ResultsProps) {
  if (response.stores.length === 0) {
    return <p className="empty">No supermarket within this distance. Try a larger radius.</p>;
  }
  return (
    <section className="results" aria-labelledby="results-heading">
      <h2 id="results-heading">Best stores for you</h2>
      <p className="hint">
        {dealsSummary(response.chains)}
        {cuisinesChosen && " Deals that fit your cuisines count for more, so they come first."}
      </p>
      <ol className="stores">
        {response.stores.map((ranked) => (
          <StoreCard
            // Names repeat across towns ("AH Breestraat" in Leiden and Utrecht).
            key={`${ranked.store.name} ${ranked.store.lat} ${ranked.store.lon}`}
            ranked={ranked}
            cuisinesChosen={cuisinesChosen}
          />
        ))}
      </ol>
    </section>
  );
}

const andList = new Intl.ListFormat("en-GB", { type: "conjunction" });

/** Whose deals were ranked, and as of which day (a stale snapshot shows its last day). */
function dealsSummary(chains: ChainDeals[]): string {
  const [only] = chains;
  if (chains.length === 1 && only) {
    return (
      `${only.chain} deals of ${formatDate(only.deals_on)}. ` +
      `Every ${only.chain} has the same deals, so for now the nearest store wins.`
    );
  }
  const each = chains.map(({ chain, deals_on }) => `${chain} (${formatDate(deals_on)})`);
  return `Deals of ${andList.format(each)}.`;
}
