import { describe, expect, it, vi } from "vitest";
import { RANKING } from "../test/fixtures";
import { ApiError, apiUrl, fetchBeer, rankStores, sha256Hex } from "./client";

function respondWith(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const REQUEST = { location: { lat: 52.1664, lon: 4.4817 }, diet: "vegetarian" } as const;

describe("sha256Hex", () => {
  it("matches the published test vectors", async () => {
    // From FIPS 180-2, and the hash of nothing.
    expect(await sha256Hex("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    expect(await sha256Hex("")).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  it("hashes UTF-8 bytes, not characters", async () => {
    // "é" is two bytes in UTF-8; hashing UTF-16 code units would differ.
    expect(await sha256Hex("é")).toBe(
      "4a99557e4033c3539de2eb65472017cad5f9557f7a0625a09f1c3f6e2ba69c4c",
    );
  });
});

describe("apiUrl", () => {
  it("is the path alone by default: the API is on the page's own domain", () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    expect(apiUrl("/api/rank")).toBe("/api/rank");
  });

  it("puts the API's address in front when the page is built with one", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.azurecontainerapps.io/");
    expect(apiUrl("/api/rank")).toBe("https://api.example.azurecontainerapps.io/api/rank");
  });

  it("is used for every request", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example");
    const fetchMock = respondWith(Response.json({ crates: [], cans: [], bottles: [] }));

    await fetchBeer();

    expect(fetchMock.mock.calls[0]?.[0]).toBe("https://api.example/api/beer");
  });
});

describe("rankStores", () => {
  it("posts the request as JSON and returns the ranking", async () => {
    const fetchMock = respondWith(Response.json(RANKING));

    await expect(rankStores(REQUEST)).resolves.toEqual(RANKING);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/rank");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual(REQUEST);
    expect(init?.headers).toEqual({
      "Content-Type": "application/json",
      // The hash of exactly the bytes sent: CloudFront's signature covers them.
      "x-amz-content-sha256": await sha256Hex(init?.body as string),
    });
  });

  it("passes on the API's reason for a 503", async () => {
    const detail = "No deals cached at data/deals/ah.json; run 'koopjeskompas fetch-deals' first.";
    respondWith(Response.json({ detail }, { status: 503 }));

    await expect(rankStores(REQUEST)).rejects.toEqual(new ApiError(503, detail));
  });

  it("names the fields that failed validation", async () => {
    const detail = [
      { loc: ["body", "location", "lat"], msg: "Input should be ≤ 90", type: "less_than_equal" },
      { loc: ["body", "radius_km"], msg: "Input should be > 0", type: "greater_than" },
    ];
    respondWith(Response.json({ detail }, { status: 422 }));

    await expect(rankStores(REQUEST)).rejects.toThrow(
      "location.lat: Input should be ≤ 90; radius_km: Input should be > 0",
    );
  });

  it("suggests starting the API when an error has no detail", async () => {
    respondWith(new Response("", { status: 502, statusText: "Bad Gateway" }));

    const error = await rankStores(REQUEST).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).message).toMatch(/502 Bad Gateway.*koopjeskompas serve/);
  });

  it("says so when the API can't be reached at all", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed")));

    await expect(rankStores(REQUEST)).rejects.toThrow(/Can't reach the API/);
  });
});
