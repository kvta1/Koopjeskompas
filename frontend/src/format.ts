/** Display formatting, kept out of the components so it can be tested on its own. */

const percentFormat = new Intl.NumberFormat("en-GB", {
  style: "percent",
  maximumFractionDigits: 0,
});

const distanceFormat = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 1,
});

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
});

/** 0.255 → "26%" */
export function formatPercent(fraction: number): string {
  return percentFormat.format(fraction);
}

/** 1.234 → "1.2 km", 0.43 → "430 m" */
export function formatDistance(km: number): string {
  if (km < 1) {
    return `${Math.round(km * 100) * 10} m`;
  }
  return `${distanceFormat.format(km)} km`;
}

/** Where a place is, on OpenStreetMap: for stores no address is known for, the only way to find them. */
export function mapUrl(lat: number, lon: number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=18/${lat}/${lon}`;
}

/** "2026-11-08" → "Sun 8 Nov" */
export function formatDate(isoDate: string): string {
  // Midnight local time: `new Date("2026-11-08")` alone means midnight UTC, which
  // is the evening before anywhere west of Greenwich.
  return dateFormat.format(new Date(`${isoDate}T00:00`));
}
