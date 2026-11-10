import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import {
  ApiError,
  fetchBeer,
  type BeerOffer,
  type BeerResponse,
  type ChainDeals,
} from "../api/client";
import { ChainBadge } from "../components/ChainBadge";
import { formatDate, formatPercent, formatPrice } from "../format";

type BeerState =
  | { status: "loading" }
  | { status: "done"; response: BeerResponse }
  | { status: "failed"; message: string };

const TABS = [
  { key: "crates", label: "Crates", empty: "No crates on offer this week." },
  { key: "cans", label: "Cans", empty: "No cans on offer this week." },
  { key: "bottles", label: "Bottles", empty: "No bottles on offer this week." },
] as const;
type Tab = (typeof TABS)[number]["key"];

/**
 * This week's beer deals of every chain, in crates, cans and bottles, cheapest per
 * litre first: the only fair way to compare a crate with a 6-pack. National, since a
 * chain's deals are the same in every store; so, unlike the stores, no location.
 */
export function BeerPage() {
  const [state, setState] = useState<BeerState>({ status: "loading" });
  const [tab, setTab] = useState<Tab>("crates");

  useEffect(() => {
    let current = true; // ignore an answer that arrives after leaving the page
    fetchBeer().then(
      (response) => current && setState({ status: "done", response }),
      (error: unknown) => {
        if (!(error instanceof ApiError)) {
          console.error(error);
        }
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        if (current) {
          setState({ status: "failed", message });
        }
      },
    );
    return () => {
      current = false;
    };
  }, []);

  return (
    <>
      <p className="tagline">Where is beer cheapest per litre this week?</p>
      {/* The Dutch alcohol advertising code's message, as beer deal sites show it. */}
      <p className="nix18">
        <strong>NIX18</strong> Geen 18, geen alcohol.
      </p>

      {state.status === "loading" && <p className="hint">Loading this week&rsquo;s beer…</p>}
      {state.status === "failed" && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.status === "done" && (
        <>
          <p className="hint">{beerSummary(state.response)}</p>
          <BeerTabs response={state.response} tab={tab} onTab={setTab} />
        </>
      )}
    </>
  );
}

interface BeerTabsProps {
  response: BeerResponse;
  tab: Tab;
  onTab: (tab: Tab) => void;
}

/**
 * Crates, cans and bottles as tabs, after the WAI-ARIA tabs pattern: only the chosen
 * tab is in the Tab order, and the arrow keys (and Home, End) move between them.
 */
function BeerTabs({ response, tab, onTab }: BeerTabsProps) {
  const id = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const index = TABS.findIndex((t) => t.key === tab);
  const chosen = TABS[index] ?? TABS[0];

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next = {
      ArrowRight: (index + 1) % TABS.length,
      ArrowLeft: (index - 1 + TABS.length) % TABS.length,
      Home: 0,
      End: TABS.length - 1,
    }[event.key];
    const target = next === undefined ? undefined : TABS[next];
    if (next !== undefined && target) {
      event.preventDefault();
      onTab(target.key);
      buttons.current[next]?.focus();
    }
  }

  return (
    <section className="beer" aria-label="Beer deals">
      <div role="tablist" aria-label="Packaging" className="tabs" onKeyDown={handleKeyDown}>
        {TABS.map((t, i) => (
          <button
            key={t.key}
            ref={(button) => {
              buttons.current[i] = button;
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${t.key}`}
            aria-selected={t.key === tab}
            aria-controls={`${id}-panel`}
            tabIndex={t.key === tab ? 0 : -1}
            onClick={() => onTab(t.key)}
          >
            {t.label} <span className="count">{response[t.key].length}</span>
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${chosen.key}`}>
        {response[chosen.key].length === 0 ? (
          <p className="empty">{chosen.empty}</p>
        ) : (
          <ol className="beer-offers">
            {response[chosen.key].map((offer, i) => (
              // Index in the key: one title can come in two sizes.
              <BeerRow key={`${i} ${offer.chain} ${offer.product}`} offer={offer} />
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function BeerRow({ offer }: { offer: BeerOffer }) {
  const pack = [offer.size, offer.units === null ? null : `${formatLitres(offer.litres)}`]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="beer-offer">
      <div className="per-litre">
        <strong>{formatPrice(offer.price_per_litre)}</strong>
        <span>per litre</span>
      </div>
      <div className="beer-what">
        <span className="deal-name">
          <ChainBadge chain={offer.chain} /> {offer.product}
          {offer.alcohol_free && (
            <span className="alcohol-free" title="Alcohol-free">
              0.0
            </span>
          )}
        </span>
        <span className="deal-details">
          {[pack, offer.mechanic, `until ${formatDate(offer.valid_to)}`]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
      <div className="beer-price">
        <strong>{formatPrice(offer.deal_price)}</strong>
        <s aria-label={`normally ${formatPrice(offer.normal_price)}`}>
          {formatPrice(offer.normal_price)}
        </s>
        <span className="discount">−{formatPercent(offer.discount)}</span>
      </div>
    </li>
  );
}

/** "7,2 l" */
function formatLitres(litres: number): string {
  return `${litres.toLocaleString("nl-NL", { maximumFractionDigits: 2 })} l`;
}

const andList = new Intl.ListFormat("en-GB", { type: "conjunction" });

/**
 * "Deals of AH (Tue 10 Nov) and Jumbo (Tue 10 Nov), …": only chains with beer on
 * offer, since a week without Lidl beer shouldn't read as if it had some.
 */
function beerSummary(response: BeerResponse): string {
  const withBeer = new Set(
    [...response.crates, ...response.cans, ...response.bottles].map((o) => o.chain),
  );
  const each = response.chains
    .filter(({ chain }) => withBeer.has(chain))
    .map(({ chain, deals_on }: ChainDeals) => `${chain} (${formatDate(deals_on)})`);
  if (each.length === 0) {
    return "No beer on offer this week.";
  }
  return `Deals of ${andList.format(each)}, the same in every store of a chain.`;
}
