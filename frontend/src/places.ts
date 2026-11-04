/** Where to rank from. Until postcode search exists, a few places in Leiden. */
export interface Place {
  name: string;
  lat: number;
  lon: number;
}

export const LEIDEN_CENTRAAL: Place = {
  name: "Leiden Centraal",
  lat: 52.1664,
  lon: 4.4817,
};

export const PLACES: readonly Place[] = [
  LEIDEN_CENTRAAL,
  { name: "Binnenstad", lat: 52.1597, lon: 4.4936 },
  { name: "Merenwijk", lat: 52.1765, lon: 4.5125 },
  { name: "Stevenshof", lat: 52.1445, lon: 4.4455 },
  { name: "Station Lammenschans", lat: 52.1465, lon: 4.4917 },
];

export const MY_LOCATION_NAME = "My location";
