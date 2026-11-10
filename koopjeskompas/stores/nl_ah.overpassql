// Every Albert Heijn supermarket in the Netherlands, from OpenStreetMap.
// Source of nl_ah.json: run with `uv run koopjeskompas fetch-stores`, which also turns
// the answer into stores (koopjeskompas/stores/osm.py). Store data © OpenStreetMap
// contributors, ODbL.
//
// The country is the area with ISO code NL, so AH's stores in Belgium (other deals)
// stay out. Stores are matched on the brand's Wikidata ID, which mappers set
// consistently, on the brand name for those without it, and on the name alone for
// stores mapped with neither (such as "AH XL Bevrijdingsplein" in Leiden). "AH to go"
// is a convenience shop, not a supermarket, so it isn't asked for.
[out:json][timeout:180];
area["ISO3166-1"="NL"]["admin_level"="2"]->.nl;
(
  nwr["shop"="supermarket"]["brand:wikidata"="Q1653985"](area.nl);
  nwr["shop"="supermarket"]["brand"="Albert Heijn"](area.nl);
  nwr["shop"="supermarket"]["name"~"^(AH|Albert Heijn)( |$)"](area.nl);
);
out center tags;
