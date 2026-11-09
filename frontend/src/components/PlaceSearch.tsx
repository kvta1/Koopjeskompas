import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { PlaceSearchError, lookupPlace, suggestPlaces, type Suggestion } from "../api/pdok";
import type { Place } from "../places";

/** Below this, a search would match half the country. */
const MIN_CHARACTERS = 2;
/** Wait for a pause in typing before asking PDOK: one request per word, not per key. */
const TYPING_PAUSE_MS = 250;

interface PlaceSearchProps {
  onChoose: (place: Place) => void;
}

/**
 * A postcode or place search that suggests matches as you type.
 *
 * Built on the WAI-ARIA combobox pattern: the input keeps the focus, and
 * `aria-activedescendant` tells screen readers which suggestion the arrow keys
 * point at, so the list works by keyboard and is announced properly.
 */
export function PlaceSearch({ onChoose }: PlaceSearchProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  /** Whether the list may show: after typing, not after choosing or Escape. */
  const [open, setOpen] = useState(false);
  /** The suggestion the arrow keys point at, or -1 for none. */
  const [active, setActive] = useState(-1);
  const [error, setError] = useState<string | null>(null);
  const listId = useId();

  const text = query.trim();
  const shown = open && text.length >= MIN_CHARACTERS ? suggestions : [];

  useEffect(() => {
    if (!open || text.length < MIN_CHARACTERS) {
      return;
    }
    // A newer keystroke cancels this search, so a slow old answer can't overwrite
    // a newer one.
    const controller = new AbortController();
    const timer = setTimeout(() => {
      suggestPlaces(text, controller.signal).then(
        (found) => {
          setSuggestions(found);
          setActive(-1);
          setError(found.length ? null : `No place found for "${text}".`);
        },
        (failure: unknown) => {
          if (failure instanceof PlaceSearchError) {
            setError(failure.message);
          }
        },
      );
    }, TYPING_PAUSE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, text]);

  async function choose(suggestion: Suggestion) {
    setOpen(false);
    setQuery(suggestion.label);
    setError(null);
    try {
      onChoose(await lookupPlace(suggestion));
    } catch (failure) {
      setError(failure instanceof PlaceSearchError ? failure.message : "Something went wrong.");
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (shown.length === 0) {
      return; // Enter submits the form as usual
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((i) => (i + 1) % shown.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((i) => (i <= 0 ? shown.length - 1 : i - 1));
        break;
      case "Enter": {
        event.preventDefault(); // pick a place, don't submit the form
        const chosen = shown[active] ?? shown[0];
        if (chosen) {
          void choose(chosen);
        }
        break;
      }
      case "Escape":
        setOpen(false);
        break;
    }
  }

  return (
    <div className="place-search">
      <input
        type="text"
        role="combobox"
        aria-label="Postcode or place"
        aria-autocomplete="list"
        aria-expanded={shown.length > 0}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        placeholder="Postcode or place, e.g. 2311 EZ or Utrecht"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => setOpen(false)}
      />
      {shown.length > 0 && (
        <ul id={listId} role="listbox" aria-label="Places" className="suggestions">
          {shown.map((suggestion, i) => (
            <li
              key={suggestion.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              // Keep the focus in the input; otherwise its blur closes the list
              // before the click arrives.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => void choose(suggestion)}
            >
              {suggestion.label}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p className="hint" role="status">
          {error}
        </p>
      )}
    </div>
  );
}
