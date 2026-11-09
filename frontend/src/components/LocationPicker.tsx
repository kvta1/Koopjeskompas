import { useState } from "react";
import { nearestAddress } from "../api/pdok";
import { MY_LOCATION_NAME, type Place } from "../places";
import { PlaceSearch } from "./PlaceSearch";

interface LocationPickerProps {
  value: Place;
  onChange: (place: Place) => void;
}

/** How rough a location may be before the page says so. */
const ROUGH_ACCURACY_M = 1000;
/** A location found this recently is still good: a second click needn't ask again. */
const REUSE_FOR_MS = 5 * 60_000;

/** A postcode or place anywhere in the Netherlands, or the browser's own location. */
export function LocationPicker({ value, onChange }: LocationPickerProps) {
  const [status, setStatus] = useState<string | null>(null);
  const canLocate = "geolocation" in navigator;

  function locate() {
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => void found(coords),
      (error) => setStatus(explain(error)),
      { timeout: 10_000, maximumAge: REUSE_FOR_MS },
    );
  }

  async function found({ latitude: lat, longitude: lon, accuracy }: GeolocationCoordinates) {
    // Name the spot, so a wrong guess is visible: "Near Damrak 1, Amsterdam".
    const near = await nearestAddress(lat, lon).catch(() => null);
    onChange({ name: near ? `Near ${near}` : MY_LOCATION_NAME, lat, lon });
    // Without GPS, browsers estimate from Wi-Fi networks or the IP address, which
    // can be kilometres off. They say how far off, so pass that on.
    setStatus(
      accuracy > ROUGH_ACCURACY_M
        ? `Your browser only knows roughly where you are (within about ${Math.round(accuracy / 1000)} km). For a better ranking, search for your postcode.`
        : null,
    );
  }

  return (
    <fieldset>
      <legend>Where are you?</legend>
      <div className="location-row">
        <PlaceSearch value={value} onChoose={onChange} />
        {canLocate && (
          <button type="button" className="secondary" onClick={locate}>
            Use my location
          </button>
        )}
      </div>
      <p className="hint" aria-live="polite">
        Ranking from <strong>{value.name}</strong>
      </p>
      {status && (
        <p className="hint" role="status">
          {status}
        </p>
      )}
    </fieldset>
  );
}

/** Why the browser gave no location, and what to do instead. */
function explain(error: GeolocationPositionError): string {
  switch (error.code) {
    case error.PERMISSION_DENIED:
      return "Location access was denied. Search for a place instead.";
    case error.TIMEOUT:
      return "Finding your location took too long. Try again, or search for a place.";
    default:
      // POSITION_UNAVAILABLE: no GPS, and the browser's estimate from Wi-Fi or the
      // IP address failed, which happens often on desktop computers.
      return "Your browser couldn't work out where you are. Search for a place instead.";
  }
}
