// Source of leiden_ah.json. Run once by hand on https://overpass-turbo.eu or
// with: curl --data-urlencode "data@leiden_ah.overpassql" https://overpass-api.de/api/interpreter
// Then keep shop=supermarket only (AH to go kiosks have a different assortment) and map
// each element to {chain: "AH", name: "AH <street>", address, location: {latitude, longitude}}.
// Last run: 2026-10-18. Store data © OpenStreetMap contributors, ODbL.
[out:json][timeout:60];
area["name"="Leiden"]["boundary"="administrative"]["admin_level"="8"]->.leiden;
(
  nwr["shop"~"^(supermarket|convenience)$"]["brand"="Albert Heijn"](area.leiden);
  nwr["shop"~"^(supermarket|convenience)$"]["name"~"^(AH|Albert Heijn)",i](area.leiden);
);
out center tags;
