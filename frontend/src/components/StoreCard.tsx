import type { Deal, RankedStore } from "../api/client";
import { formatDate, formatDistance, formatPercent, mapUrl } from "../format";

interface StoreCardProps {
  ranked: RankedStore;
  cuisinesChosen: boolean;
  /** Whether its deals start shown: for the best store of each chain. */
  open: boolean;
}

/** One ranked store and the deals that earned its score. */
export function StoreCard({ ranked, cuisinesChosen, open }: StoreCardProps) {
  const { store, distance_km: distanceKm, top_deals: deals } = ranked;
  const place = placeName(store.name, store.chain);
  return (
    <li className="store">
      <div className="store-header">
        <span className="rank" aria-label={`Rank ${ranked.rank}`}>
          {ranked.rank}
        </span>
        <div className="store-name">
          <h3>
            <span className={`chain chain-${store.chain.toLowerCase()}`}>{store.chain}</span>
            {place && ` ${place}`}
          </h3>
          <p className="address">
            {store.address ?? "No address known"} ·{" "}
            <a href={mapUrl(store.lat, store.lon)} target="_blank" rel="noreferrer">
              On the map
            </a>
          </p>
        </div>
        <span className="distance">{formatDistance(distanceKm)}</span>
      </div>
      {deals.length === 0 ? (
        <p className="hint">No deals that fit your preferences.</p>
      ) : (
        // Native disclosure. Stores of one chain share their deals, so only the best
        // store of each chain starts open: one list per chain, not one per store.
        <details open={open}>
          <summary>
            {deals.length === 1 ? "Its best deal" : `Its ${deals.length} best deals`}
          </summary>
          <ul className="deals">
            {deals.map((deal, index) => (
              // Index in the key: a product name may appear twice in one week.
              <DealRow
                key={`${index} ${deal.product_name}`}
                deal={deal}
                // Relevance is 1 for a deal that fits a chosen cuisine (and for
                // every deal when none is chosen), lower otherwise.
                fitsCuisines={cuisinesChosen && deal.relevance === 1}
              />
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

/**
 * The store's name without its chain, which the badge shows: "Jumbo Molenplein"
 * → "Molenplein". A store mapped without an address is named after its chain alone,
 * so nothing is left: null.
 */
function placeName(name: string, chain: string): string | null {
  if (name === chain) {
    return null;
  }
  return name.startsWith(`${chain} `) ? name.slice(chain.length + 1) : name;
}

function DealRow({ deal, fitsCuisines }: { deal: Deal; fitsCuisines: boolean }) {
  const details = [
    deal.mechanic,
    deal.products_counted > 0 &&
      `median of ${deal.products_counted} ${deal.products_counted === 1 ? "product" : "products"}`,
    `until ${formatDate(deal.valid_to)}`,
  ].filter(Boolean);
  return (
    <li className="deal">
      <span className="discount" title="Share of the normal price you save">
        −{formatPercent(deal.discount)}
      </span>
      <span>
        <span className="deal-name">
          {deal.product_name}
          {fitsCuisines && <span className="fit">fits your cuisines</span>}
        </span>
        <span className="deal-details">{details.join(" · ")}</span>
      </span>
    </li>
  );
}
