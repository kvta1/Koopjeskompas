import { useState } from "react";
import { MY_LOCATION_NAME, PLACES, type Place } from "../places";

interface LocationPickerProps {
  value: Place;
  onChange: (place: Place) => void;
}

/** A preset place in Leiden, or the browser's own location. */
export function LocationPicker({ value, onChange }: LocationPickerProps) {
  const [myLocation, setMyLocation] = useState<Place | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const places = myLocation ? [myLocation, ...PLACES] : PLACES;
  const canLocate = "geolocation" in navigator;

  function locate() {
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const place = {
          name: MY_LOCATION_NAME,
          lat: coords.latitude,
          lon: coords.longitude,
        };
        setMyLocation(place);
        onChange(place);
        setStatus(null);
      },
      (error) => {
        setStatus(
          error.code === error.PERMISSION_DENIED
            ? "Location access was denied. Pick a place instead."
            : "Couldn't find your location. Pick a place instead.",
        );
      },
      { timeout: 10_000 },
    );
  }

  return (
    <fieldset>
      <legend>Where are you?</legend>
      <div className="location-row">
        <select
          aria-label="Place"
          value={value.name}
          onChange={(event) => {
            const place = places.find((p) => p.name === event.target.value);
            if (place) {
              onChange(place);
            }
          }}
        >
          {places.map((place) => (
            <option key={place.name} value={place.name}>
              {place.name}
            </option>
          ))}
        </select>
        {canLocate && (
          <button type="button" className="secondary" onClick={locate}>
            Use my location
          </button>
        )}
      </div>
      {status && (
        <p className="hint" role="status">
          {status}
        </p>
      )}
    </fieldset>
  );
}
