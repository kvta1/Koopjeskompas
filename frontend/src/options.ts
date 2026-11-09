/**
 * The choices the form offers, with their labels.
 *
 * `Record<Diet, string>` makes the label tables exhaustive: when the API gains a
 * diet or cuisine, `npm run gen:api` adds it to the generated types and the build
 * fails until it has a label here too.
 */
import type { Cuisine, Diet } from "./api/client";

export const DIET_LABELS: Record<Diet, string> = {
  none: "No restriction",
  vegetarian: "Vegetarian",
  vegan: "Vegan",
};

export const CUISINE_LABELS: Record<Cuisine, string> = {
  middle_eastern: "Middle Eastern",
  italian: "Italian",
  asian: "Asian",
  mexican: "Mexican",
  indian: "Indian",
};

// 20 km, for the countryside, where the nearest AH can be well beyond 10 km.
export const RADIUS_OPTIONS_KM = [1, 2, 5, 10, 20] as const;
export const DEFAULT_RADIUS_KM = 5; // the API's default

/** Typed `Object.keys`: TypeScript types it as `string[]` on purpose, since an
 * object may have more keys than its type says. These tables are our own. */
export function keysOf<K extends string>(labels: Record<K, string>): K[] {
  return Object.keys(labels) as K[];
}
