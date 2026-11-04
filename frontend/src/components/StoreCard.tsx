import type { Deal, RankedStore } from "../api/client";
import { formatDate, formatDistance, formatPercent } from "../format";

interface StoreCardProps {
  ranked: RankedStore;
  cuisinesChosen: boolean;
}

/** One ranked store and the deals that earned its score. */
export function StoreCard({ ranked, cuisinesChosen }: StoreCardProps) {
  const { rank, store, distance_km: distanceKm, top_deals: deals } = ranked;
  return (
    <li className="store">
      <div className="store-header">
        <span className="rank" aria-label={`Rank ${rank}`}>
          {rank}
        </span>
        <div className="store-name">
          <h3>{store.name}</h3>
          {store.address && <p className="address">{store.address}</p>}
        </div>
        <span className="distance">{formatDistance(distanceKm)}</span>
      </div>
      {deals.length === 0 ? (
        <p className="hint">No deals that fit your preferences.</p>
      ) : (
        // Native disclosure: only the best store starts open, as every AH has the
        // same deals and several identical open lists would bury the ranking.
        <details open={rank === 1}>
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
