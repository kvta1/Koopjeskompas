import type { BeerResponse, RankResponse } from "../api/client";

/** A response in the shape the API sends, typed so it can't drift from the schema. */
export const RANKING: RankResponse = {
  ranked_on: "2026-11-04",
  chains: [{ chain: "AH", deals_on: "2026-11-04" }],
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

const offer = {
  deal: "Alle Hertog Jan, Amstel, Bavaria of Warsteiner multipacks",
  mechanic: "25% KORTING",
  discount: 0.25,
  alcohol_free: false,
  valid_from: "2026-11-09",
  valid_to: "2026-11-15",
};

/** A beer response with two crates, one can and no bottles. */
export const BEER: BeerResponse = {
  ranked_on: "2026-11-10",
  chains: [
    { chain: "AH", deals_on: "2026-11-10" },
    { chain: "Jumbo", deals_on: "2026-11-10" },
    { chain: "Lidl", deals_on: "2026-11-10" }, // no beer this week
  ],
  crates: [
    {
      ...offer,
      chain: "AH",
      product: "Hertog Jan Pilsener bier krat",
      packaging: "krat",
      size: "24 x 30 cl",
      units: 24,
      litres: 7.2,
      normal_price: 21.32,
      deal_price: 15.99,
      price_per_litre: 2.22,
    },
    {
      ...offer,
      chain: "Jumbo",
      deal: "Pils van Alfa, Warsteiner, Stella Artois of Corona",
      mechanic: "25% korting",
      product: "Stella Artois Krat 24x330ML",
      packaging: "krat",
      size: "24x330ML",
      units: 24,
      litres: 7.92,
      normal_price: 23.99,
      deal_price: 17.99,
      price_per_litre: 2.27,
    },
  ],
  cans: [
    {
      ...offer,
      chain: "AH",
      product: "Heineken Premium pilsener 0.0 6-pack",
      packaging: "blik",
      size: "6 x 0,33 l",
      units: 6,
      litres: 1.98,
      normal_price: 6.65,
      deal_price: 4.99,
      price_per_litre: 2.52,
      alcohol_free: true,
    },
  ],
  bottles: [],
};
