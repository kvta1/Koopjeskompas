/** Where to rank from: a place found by the place search, or the browser's location. */
export interface Place {
  name: string;
  lat: number;
  lon: number;
}

/** Where the page starts, until a place is chosen. */
export const LEIDEN_CENTRAAL: Place = {
  name: "Leiden Centraal",
  lat: 52.1664,
  lon: 4.4817,
};

export const MY_LOCATION_NAME = "My location";
