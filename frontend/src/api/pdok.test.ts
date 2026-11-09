import { describe, expect, it, vi } from "vitest";
import { PlaceSearchError, lookupPlace, parsePoint, suggestPlaces } from "./pdok";

/** Shaped like PDOK's answers, trimmed to the fields asked for. */
const SUGGEST = {
  response: {
    numFound: 2,
    docs: [
      { id: "pcd-1320970aedbf2bbb17d29c88bb92975d", weergavenaam: "Begijnhof, 2311EZ Leiden" },
      { id: "pcd-72e830fb2d77642a4dea3e093efba1fe", weergavenaam: "Rapenburg, 2311EZ Leiden" },
    ],
  },
};
const LOOKUP = {
  response: {
    docs: [
      { id: "pcd-1320970aedbf2bbb17d29c88bb92975d", centroide_ll: "POINT(4.48691613 52.15639235)" },
    ],
  },
};

function respondWith(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("parsePoint", () => {
  it("reads longitude first, as WKT writes it", () => {
    expect(parsePoint("POINT(4.48691613 52.15639235)")).toEqual({
      lat: 52.15639235,
      lon: 4.48691613,
    });
  });

  it("refuses anything else", () => {
    expect(() => parsePoint("POLYGON((4 52, 5 53))")).toThrow(PlaceSearchError);
  });
});

describe("suggestPlaces", () => {
  it("asks for postcodes, towns, streets and addresses, and returns their names", async () => {
    const fetchMock = respondWith(Response.json(SUGGEST));

    const suggestions = await suggestPlaces("2311 ez");

    expect(suggestions).toEqual([
      { id: "pcd-1320970aedbf2bbb17d29c88bb92975d", label: "Begijnhof, 2311EZ Leiden" },
      { id: "pcd-72e830fb2d77642a4dea3e093efba1fe", label: "Rapenburg, 2311EZ Leiden" },
    ]);
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(url.origin + url.pathname).toBe(
      "https://api.pdok.nl/bzk/locatieserver/search/v3_1/suggest",
    );
    expect(url.searchParams.get("q")).toBe("2311 ez");
    expect(url.searchParams.get("fq")).toBe("type:(postcode OR woonplaats OR weg OR adres)");
  });

  it("explains a failed search", async () => {
    respondWith(new Response("", { status: 503 }));
    await expect(suggestPlaces("leiden")).rejects.toThrow("The place search answered 503");
  });

  it("explains an unreachable PDOK", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));
    await expect(suggestPlaces("leiden")).rejects.toThrow("Can't reach the place search");
  });

  it("lets a cancelled search stay cancelled", async () => {
    const abort = new DOMException("replaced", "AbortError");
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(abort));
    await expect(suggestPlaces("leiden")).rejects.toBe(abort);
  });
});

describe("lookupPlace", () => {
  it("gives the chosen place its coordinates", async () => {
    const fetchMock = respondWith(Response.json(LOOKUP));

    const place = await lookupPlace({
      id: "pcd-1320970aedbf2bbb17d29c88bb92975d",
      label: "Begijnhof, 2311EZ Leiden",
    });

    expect(place).toEqual({ name: "Begijnhof, 2311EZ Leiden", lat: 52.15639235, lon: 4.48691613 });
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(url.pathname.endsWith("/lookup")).toBe(true);
    expect(url.searchParams.get("id")).toBe("pcd-1320970aedbf2bbb17d29c88bb92975d");
  });

  it("explains a place that's gone", async () => {
    respondWith(Response.json({ response: { docs: [] } }));
    await expect(lookupPlace({ id: "x", label: "Nowhere" })).rejects.toThrow(
      'PDOK no longer knows "Nowhere"',
    );
  });
});
