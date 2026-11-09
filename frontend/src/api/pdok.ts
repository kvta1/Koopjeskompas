/**
 * Place search with PDOK Locatieserver, the Dutch government's free geocoder.
 *
 * The browser asks PDOK directly, not through our API: PDOK allows calls from any
 * origin and needs no key, so a search costs no Lambda call. Two steps, as PDOK
 * intends: `suggest` while typing (names only), then `lookup` for the one chosen
 * (with its coordinates).
 */
import type { Place } from "../places";

const PDOK = "https://api.pdok.nl/bzk/locatieserver/search/v3_1";

/**
 * What can be searched for: a postcode, a town, a street or an address. PDOK also
 * knows municipalities, provinces and land parcels; those are too coarse or too
 * odd to rank from.
 */
const PLACE_TYPES = "type:(postcode OR woonplaats OR weg OR adres)";
const MAX_SUGGESTIONS = 6;

export interface Suggestion {
  id: string;
  /** PDOK's display name, e.g. "Begijnhof, 2311EZ Leiden". */
  label: string;
}

/** A failed place search, with a message that can be shown as is. */
export class PlaceSearchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PlaceSearchError";
  }
}

interface PdokResponse<Doc> {
  response: { docs: Doc[] };
}

/** Places whose name matches what has been typed so far, best first. */
export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<Suggestion[]> {
  const params = new URLSearchParams({
    q: query,
    fq: PLACE_TYPES,
    rows: String(MAX_SUGGESTIONS),
    fl: "id,weergavenaam",
  });
  const body = await getJson<PdokResponse<{ id: string; weergavenaam: string }>>(
    `${PDOK}/suggest?${params}`,
    signal,
  );
  return body.response.docs.map((doc) => ({ id: doc.id, label: doc.weergavenaam }));
}

/** The chosen suggestion, with its coordinates. */
export async function lookupPlace(suggestion: Suggestion, signal?: AbortSignal): Promise<Place> {
  const params = new URLSearchParams({ id: suggestion.id, fl: "id,centroide_ll" });
  const body = await getJson<PdokResponse<{ centroide_ll: string }>>(
    `${PDOK}/lookup?${params}`,
    signal,
  );
  const doc = body.response.docs[0];
  if (!doc) {
    throw new PlaceSearchError(`PDOK no longer knows "${suggestion.label}". Try another.`);
  }
  return { name: suggestion.label, ...parsePoint(doc.centroide_ll) };
}

/**
 * "POINT(4.48691613 52.15639235)" → { lat: 52.156…, lon: 4.486… }.
 *
 * Mind the order: WKT, the format PDOK uses, writes x before y, so longitude comes
 * first. Swapped, Leiden would land in the Indian Ocean.
 */
export function parsePoint(wkt: string): { lat: number; lon: number } {
  const match = /^POINT\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)$/.exec(wkt.trim());
  if (!match?.[1] || !match[2]) {
    throw new PlaceSearchError(`Can't read the location "${wkt}".`);
  }
  return { lon: Number(match[1]), lat: Number(match[2]) };
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error; // a newer search replaced this one: not a failure to report
    }
    throw new PlaceSearchError("Can't reach the place search. Check your connection.");
  }
  if (!response.ok) {
    throw new PlaceSearchError(`The place search answered ${response.status}. Try again.`);
  }
  // Trusted rather than validated, like our own API: PDOK's response format is
  // documented and versioned (v3_1 in the URL).
  return (await response.json()) as T;
}
