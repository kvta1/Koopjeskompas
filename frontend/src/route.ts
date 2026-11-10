import { useEffect, useState } from "react";

/** The two sections of the page. */
export type Route = "stores" | "beer";

export const BEER_HASH = "#/beer";

function routeOf(hash: string): Route {
  return hash === BEER_HASH ? "beer" : "stores";
}

/**
 * Which section the address points at: `#/beer`, or the stores by default.
 *
 * Two sections don't need a router library: the address's hash changes when a link
 * is followed or Back is pressed, and the browser announces that with `hashchange`.
 * A hash, not a path, because the page is static files on S3 + CloudFront: `/beer`
 * would ask the server for a file that isn't there.
 */
export function useRoute(): Route {
  const [route, setRoute] = useState(() => routeOf(window.location.hash));
  useEffect(() => {
    const update = () => setRoute(routeOf(window.location.hash));
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}
