import type { RankResponse } from "../api/client";

/** A response in the shape the API sends, typed so it can't drift from the schema. */
export const RANKING: RankResponse = {
  ranked_on: "2026-11-04",
  stores: [
    {
      rank: 1,
      store: {
        chain: "AH",
        name: "AH Breestraat",
        address: "Breestraat 130, Leiden",
        lat: 52.157,
        lon: 4.492,
      },
      score: 1.21,
      basket_score: 1.79,
      distance_km: 1.08,
      top_deals: [
        {
          product_name: "Alle AH Verse pizza's",
          category: "Maaltijden, salades",
          mechanic: "2 VOOR 12.00",
          discount: 0.1292,
          relevance: 1,
          value: 0.1292,
          products_counted: 3,
          valid_from: "2026-11-02",
          valid_to: "2026-11-08",
        },
        {
          product_name: "AH Hummus naturel",
          category: null,
          mechanic: null,
          discount: 0.25,
          relevance: 0.2,
          value: 0.05,
          products_counted: 0,
          valid_from: "2026-11-02",
          valid_to: "2026-11-08",
        },
      ],
    },
    {
      rank: 2,
      store: { chain: "AH", name: "AH Hooigracht", address: null, lat: 52.16, lon: 4.497 },
      score: 0.95,
      basket_score: 1.79,
      distance_km: 1.31,
      top_deals: [],
    },
  ],
};
