import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RankRequest } from "./api/client";
import { App } from "./App";
import { RANKING } from "./test/fixtures";

/** Stub fetch with one response, and return the request bodies it received. */
function stubApi(response: Response): RankRequest[] {
  const requests: RankRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(async (_url, init) => {
      requests.push(JSON.parse(init?.body as string) as RankRequest);
      return response;
    }),
  );
  return requests;
}

async function submit() {
  await userEvent.click(screen.getByRole("button", { name: "Find the best deals" }));
}

describe("App", () => {
  it("sends the chosen location and preferences", async () => {
    const requests = stubApi(Response.json(RANKING));
    render(<App />);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Place" }), "Merenwijk");
    await userEvent.click(screen.getByRole("radio", { name: "Vegetarian" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Italian" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Indian" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Italian" })); // and off again
    await userEvent.click(screen.getByRole("checkbox", { name: "Gluten-free" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Within" }), "2");
    await submit();

    expect(requests).toEqual([
      {
        location: { lat: 52.1765, lon: 4.5125 },
        diet: "vegetarian",
        cuisines: ["indian"],
        gluten_free: true,
        lactose_free: false,
        radius_km: 2,
      },
    ]);
  });

  it("shows the ranked stores with the deals behind their score", async () => {
    stubApi(Response.json(RANKING));
    render(<App />);
    await submit();

    const [best, second] = await screen.findAllByRole("heading", { level: 3 });
    expect(best).toHaveTextContent("AH Breestraat");
    expect(second).toHaveTextContent("AH Hooigracht");

    expect(screen.getByText("Alle AH Verse pizza's")).toBeVisible();
    expect(screen.getByText("2 VOOR 12.00 · median of 3 products · until Sun 8 Nov")).toBeVisible();
    expect(screen.getByText("−13%")).toBeVisible();
    expect(screen.getByText("No deals that fit your preferences.")).toBeInTheDocument();
    expect(screen.getByText(/bonus deals on Wed 4 Nov/)).toBeInTheDocument();
  });

  it("marks the deals that fit the chosen cuisines", async () => {
    stubApi(Response.json(RANKING));
    render(<App />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Italian" }));
    await submit();

    expect(await screen.findByText("fits your cuisines")).toBeVisible(); // pizzas only
    expect(screen.getAllByText("fits your cuisines")).toHaveLength(1);
    expect(screen.getByText(/fit your cuisines count for more/)).toBeInTheDocument();
  });

  it("marks nothing when no cuisine is chosen", async () => {
    stubApi(Response.json(RANKING));
    render(<App />);
    await submit();

    await screen.findAllByRole("heading", { level: 3 });
    expect(screen.queryByText("fits your cuisines")).not.toBeInTheDocument();
  });

  it("says when no store is within the radius", async () => {
    stubApi(Response.json({ ranked_on: "2026-11-04", stores: [] }));
    render(<App />);
    await submit();

    expect(await screen.findByText(/No Albert Heijn within this distance/)).toBeInTheDocument();
  });

  it("shows the API's error message", async () => {
    stubApi(Response.json({ detail: "No deals cached yet." }, { status: 503 }));
    render(<App />);
    await submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("No deals cached yet.");
  });

  it("disables the button while a ranking is on its way", async () => {
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(() => new Promise((resolve) => (answer = resolve))),
    );
    render(<App />);
    await submit();

    expect(screen.getByRole("button", { name: "Ranking…" })).toBeDisabled();
    answer(Response.json(RANKING));
    expect(await screen.findByRole("button", { name: "Find the best deals" })).toBeEnabled();
  });

  it("can rank from the browser's location", async () => {
    const requests = stubApi(Response.json(RANKING));
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: {
        getCurrentPosition: (onSuccess: PositionCallback) =>
          onSuccess({ coords: { latitude: 52.15, longitude: 4.47 } } as GeolocationPosition),
      },
    });
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));
    expect(screen.getByRole("combobox", { name: "Place" })).toHaveValue("My location");
    await submit();

    expect(requests[0]?.location).toEqual({ lat: 52.15, lon: 4.47 });
  });
});
