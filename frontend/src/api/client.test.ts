import { describe, expect, it, vi } from "vitest";
import { RANKING } from "../test/fixtures";
import { ApiError, rankStores } from "./client";

function respondWith(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const REQUEST = { location: { lat: 52.1664, lon: 4.4817 }, diet: "vegetarian" } as const;

describe("rankStores", () => {
  it("posts the request as JSON and returns the ranking", async () => {
    const fetchMock = respondWith(Response.json(RANKING));

    await expect(rankStores(REQUEST)).resolves.toEqual(RANKING);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/rank");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init?.body as string)).toEqual(REQUEST);
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
