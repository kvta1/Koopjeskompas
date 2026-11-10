import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RankRequest } from "./api/client";
import { App } from "./App";
import { RANKING } from "./test/fixtures";

const BEGIJNHOF = { id: "pcd-1320970aedbf2bbb17d29c88bb92975d", label: "Begijnhof, 2311EZ Leiden" };
const RAPENBURG = { id: "pcd-72e830fb2d77642a4dea3e093efba1fe", label: "Rapenburg, 2311EZ Leiden" };
const POINTS: Record<string, string> = {
  [BEGIJNHOF.id]: "POINT(4.48691613 52.15639235)",
  [RAPENBURG.id]: "POINT(4.4865 52.1572)",
};

/**
 * Stub fetch: our API answers `response`, and PDOK's place search answers like
 * PDOK does, with two places for any query. Returns the ranking requests sent.
 */
function stubApi(response: Response): RankRequest[] {
  const requests: RankRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/suggest")) {
        const docs = [BEGIJNHOF, RAPENBURG].map((p) => ({ id: p.id, weergavenaam: p.label }));
        return Response.json({ response: { docs } });
      }
      if (url.pathname.endsWith("/reverse")) {
        const docs = [{ weergavenaam: "Begijnhof 1, 2311EZ Leiden", afstand: 3.2 }];
        return Response.json({ response: { docs } });
      }
      if (url.pathname.endsWith("/lookup")) {
        const id = url.searchParams.get("id") ?? "";
        return Response.json({ response: { docs: [{ id, centroide_ll: POINTS[id] }] } });
      }
      requests.push(JSON.parse(init?.body as string) as RankRequest);
      return response;
    }),
  );
  return requests;
}

function placeSearch() {
  return screen.getByRole("combobox", { name: "Postcode or place" });
}

/** The suggested places, once they've arrived (not the radius dropdown's options). */
async function suggestions() {
  return within(await screen.findByRole("listbox", { name: "Places" })).getAllByRole("option");
}

async function submit() {
  await userEvent.click(screen.getByRole("button", { name: "Find the best deals" }));
}

describe("App", () => {
  it("sends the chosen location and preferences", async () => {
    const requests = stubApi(Response.json(RANKING));
    render(<App />);

    await userEvent.type(placeSearch(), "2311 ez");
    await userEvent.click(
      within(await screen.findByRole("listbox")).getByRole("option", { name: RAPENBURG.label }),
    );
    await screen.findByText(RAPENBURG.label, { selector: "strong" });
    await userEvent.click(screen.getByRole("radio", { name: "Vegetarian" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Italian" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Indian" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Italian" })); // and off again
    await userEvent.click(screen.getByRole("checkbox", { name: "Gluten-free" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Within" }), "2");
    await submit();

    expect(requests).toEqual([
      {
        location: { lat: 52.1572, lon: 4.4865 },
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
    const { options } = stubLocation({ latitude: 52.1564, longitude: 4.4869, accuracy: 20 });
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));

    // The box names the spot, so a wrong guess would be plain to see.
    expect(await screen.findByDisplayValue("Near Begijnhof 1, 2311EZ Leiden")).toBe(placeSearch());
    expect(screen.queryByRole("status")).not.toBeInTheDocument(); // accurate: no warning
    expect(options()?.maximumAge).toBeGreaterThan(0); // a second click reuses it
    await submit();
    expect(requests[0]?.location).toEqual({ lat: 52.1564, lon: 4.4869 });
  });
});

/** Stub the browser's geolocation with a position, or with a failure code. */
function stubLocation(outcome: Partial<GeolocationCoordinates> | { code: number }) {
  let lastOptions: PositionOptions | undefined;
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: {
      getCurrentPosition: (
        onSuccess: PositionCallback,
        onError: PositionErrorCallback,
        options?: PositionOptions,
      ) => {
        lastOptions = options;
        if ("code" in outcome) {
          onError({
            code: outcome.code,
            PERMISSION_DENIED: 1,
            POSITION_UNAVAILABLE: 2,
            TIMEOUT: 3,
          } as GeolocationPositionError);
        } else {
          onSuccess({ coords: outcome } as GeolocationPosition);
        }
      },
    },
  });
  return { options: () => lastOptions };
}

describe("Use my location", () => {
  it("warns when the browser only knows roughly where you are", async () => {
    stubApi(Response.json(RANKING));
    // What a laptop without GPS often reports: an IP-based guess, 25 km wide.
    stubLocation({ latitude: 52.3728, longitude: 4.8936, accuracy: 25_000 });
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "only knows roughly where you are (within about 25 km)",
    );
  });

  it.each([
    [1, "Location access was denied"],
    [2, "Your browser couldn't work out where you are"],
    [3, "Finding your location took too long"],
  ])("explains failure code %i", async (code, message) => {
    stubApi(Response.json(RANKING));
    stubLocation({ code });
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));

    expect(await screen.findByRole("status")).toHaveTextContent(message);
    expect(screen.getByText("Leiden Centraal", { selector: "strong" })).toBeVisible();
  });
});

describe("the place search", () => {
  it("starts from Leiden Centraal", async () => {
    const requests = stubApi(Response.json(RANKING));
    render(<App />);

    expect(screen.getByText("Leiden Centraal", { selector: "strong" })).toBeVisible();
    await submit();
    expect(requests[0]?.location).toEqual({ lat: 52.1664, lon: 4.4817 });
  });

  it("suggests places as you type, and works by keyboard", async () => {
    const requests = stubApi(Response.json(RANKING));
    render(<App />);

    await userEvent.type(placeSearch(), "2311 ez");
    const options = await suggestions();
    expect(options.map((o) => o.textContent)).toEqual([BEGIJNHOF.label, RAPENBURG.label]);
    expect(placeSearch()).toHaveAttribute("aria-expanded", "true");

    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    expect(placeSearch()).toHaveAttribute("aria-activedescendant", options[1]?.id);
    await userEvent.keyboard("{Enter}");

    expect(await screen.findByText(RAPENBURG.label, { selector: "strong" })).toBeVisible();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(requests).toEqual([]); // Enter picked a place; it didn't submit the form
    await submit();
    expect(requests[0]?.location).toEqual({ lat: 52.1572, lon: 4.4865 });
  });

  it("takes the first suggestion on Enter, and closes on Escape", async () => {
    stubApi(Response.json(RANKING));
    render(<App />);

    await userEvent.type(placeSearch(), "begijnhof");
    await suggestions();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    await userEvent.type(placeSearch(), " leiden");
    await suggestions();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByText(BEGIJNHOF.label, { selector: "strong" })).toBeVisible();
  });

  it("waits for two characters", async () => {
    stubApi(Response.json(RANKING));
    render(<App />);

    await userEvent.type(placeSearch(), "2");
    await new Promise((resolve) => setTimeout(resolve, 400)); // past the typing pause
    expect(fetch).not.toHaveBeenCalled();
  });

  it("explains a failing place search, and keeps the last place", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(new Response("", { status: 503 })),
    );
    render(<App />);

    await userEvent.type(placeSearch(), "utrecht");
    expect(await screen.findByRole("status")).toHaveTextContent("The place search answered 503");
    expect(screen.getByText("Leiden Centraal", { selector: "strong" })).toBeVisible();
  });
});
