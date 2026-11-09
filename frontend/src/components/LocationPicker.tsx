import { useState } from "react";
import { MY_LOCATION_NAME, type Place } from "../places";
import { PlaceSearch } from "./PlaceSearch";

interface LocationPickerProps {
  value: Place;
  onChange: (place: Place) => void;
}

/** A postcode or place anywhere in the Netherlands, or the browser's own location. */
export function LocationPicker({ value, onChange }: LocationPickerProps) {
  const [status, setStatus] = useState<string | null>(null);
  const canLocate = "geolocation" in navigator;

  function locate() {
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        onChange({ name: MY_LOCATION_NAME, lat: coords.latitude, lon: coords.longitude });
        setStatus(null);
      },
      (error) => {
        setStatus(
          error.code === error.PERMISSION_DENIED
            ? "Location access was denied. Search for a place instead."
            : "Couldn't find your location. Search for a place instead.",
        );
      },
      { timeout: 10_000 },
    );
  }

  return (
    <fieldset>
      <legend>Where are you?</legend>
      <div className="location-row">
        <PlaceSearch onChoose={onChange} />
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
