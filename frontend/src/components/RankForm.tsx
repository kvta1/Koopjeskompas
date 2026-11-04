import { useState, type FormEvent } from "react";
import type { Cuisine, Diet, RankRequest } from "../api/client";
import {
  CUISINE_LABELS,
  DEFAULT_RADIUS_KM,
  DIET_LABELS,
  RADIUS_OPTIONS_KM,
  keysOf,
} from "../options";
import { LEIDEN_CENTRAAL, type Place } from "../places";
import { LocationPicker } from "./LocationPicker";

interface RankFormProps {
  busy: boolean;
  onSubmit: (request: RankRequest) => void;
}

/** The user's location and preferences, turned into a `RankRequest` on submit. */
export function RankForm({ busy, onSubmit }: RankFormProps) {
  const [place, setPlace] = useState<Place>(LEIDEN_CENTRAAL);
  const [diet, setDiet] = useState<Diet>("none");
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [glutenFree, setGlutenFree] = useState(false);
  const [lactoseFree, setLactoseFree] = useState(false);
  const [radiusKm, setRadiusKm] = useState(DEFAULT_RADIUS_KM);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); // no page reload: the request goes through fetch
    onSubmit({
      location: { lat: place.lat, lon: place.lon },
      diet,
      cuisines,
      gluten_free: glutenFree,
      lactose_free: lactoseFree,
      radius_km: radiusKm,
    });
  }

  function toggleCuisine(cuisine: Cuisine, checked: boolean) {
    // A new array rather than a changed one: React re-renders when state is
    // replaced, not when it is mutated in place.
    setCuisines((current) =>
      checked ? [...current, cuisine] : current.filter((c) => c !== cuisine),
    );
  }

  return (
    <form className="rank-form" onSubmit={handleSubmit}>
      <LocationPicker value={place} onChange={setPlace} />

      <fieldset>
        <legend>Diet</legend>
        <div className="choices">
          {keysOf(DIET_LABELS).map((value) => (
            <label key={value} className="choice">
              <input
                type="radio"
                name="diet"
                value={value}
                checked={diet === value}
                onChange={() => setDiet(value)}
              />
              {DIET_LABELS[value]}
            </label>
          ))}
        </div>
        <div className="choices">
          <label className="choice">
            <input
              type="checkbox"
              checked={glutenFree}
              onChange={(event) => setGlutenFree(event.target.checked)}
            />
            Gluten-free
          </label>
          <label className="choice">
            <input
              type="checkbox"
              checked={lactoseFree}
              onChange={(event) => setLactoseFree(event.target.checked)}
            />
            Lactose-free
          </label>
        </div>
        <p className="hint">These are strict: deals that don&apos;t fit are left out.</p>
      </fieldset>

      <fieldset>
        <legend>Cuisines you like</legend>
        <div className="choices">
          {keysOf(CUISINE_LABELS).map((cuisine) => (
            <label key={cuisine} className="choice">
              <input
                type="checkbox"
                checked={cuisines.includes(cuisine)}
                onChange={(event) => toggleCuisine(cuisine, event.target.checked)}
              />
              {CUISINE_LABELS[cuisine]}
            </label>
          ))}
        </div>
        <p className="hint">Deals that fit these count for more.</p>
      </fieldset>

      <div className="form-footer">
        <label className="radius">
          Within{" "}
          <select value={radiusKm} onChange={(event) => setRadiusKm(Number(event.target.value))}>
            {RADIUS_OPTIONS_KM.map((km) => (
              <option key={km} value={km}>
                {km} km
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Ranking…" : "Find the best deals"}
        </button>
      </div>
    </form>
  );
}
