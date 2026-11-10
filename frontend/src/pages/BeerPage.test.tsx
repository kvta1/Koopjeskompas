import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { BEER } from "../test/fixtures";

function stubBeer(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openBeer() {
  render(<App />);
  await userEvent.click(screen.getByRole("link", { name: "Beer" }));
}

beforeEach(() => {
  window.location.hash = "";
});
afterEach(() => {
  window.location.hash = "";
});

describe("the beer section", () => {
  it("is a section of its own, reached from the navigation", async () => {
    const fetchMock = stubBeer(Response.json(BEER));
    await openBeer();

    expect(screen.getByRole("link", { name: "Beer" })).toHaveAttribute("aria-current", "page");
    expect(window.location.hash).toBe("#/beer");
    expect(fetchMock).toHaveBeenCalledWith("/api/beer", undefined);
    // Not the stores' form: no location needed for national deals.
    expect(screen.queryByRole("combobox", { name: "Postcode or place" })).not.toBeInTheDocument();
  });

  it("shows NIX18", async () => {
    stubBeer(Response.json(BEER));
    await openBeer();
    expect(screen.getByText("NIX18")).toBeVisible();
    expect(screen.getByText(/Geen 18, geen alcohol/)).toBeVisible();
  });

  it("starts with crates, cheapest per litre first", async () => {
    stubBeer(Response.json(BEER));
    await openBeer();

    const crates = await screen.findByRole("tab", { name: /Crates/ });
    expect(crates).toHaveAttribute("aria-selected", "true");
    expect(crates).toHaveTextContent("Crates 2");
    const [first, second] = within(screen.getByRole("tabpanel")).getAllByRole("listitem");
    expect(first).toHaveTextContent("Hertog Jan Pilsener bier krat");
    expect(first).toHaveTextContent("€ 2,22per litre");
    expect(first).toHaveTextContent("24 x 30 cl · 7,2 l · 25% KORTING · until Sun 15 Nov");
    expect(first).toHaveTextContent("€ 15,99");
    expect(within(first!).getByLabelText("normally € 21,32")).toBeVisible();
    expect(second).toHaveTextContent("Stella Artois Krat 24x330ML");
    // Lidl has a snapshot but no beer this week: not named.
    expect(screen.getByText(/^Deals of AH \(Tue 10 Nov\) and Jumbo \(Tue 10 Nov\),/)).toBeVisible();
  });

  it("switches packaging by click and by arrow keys", async () => {
    stubBeer(Response.json(BEER));
    await openBeer();

    await userEvent.click(await screen.findByRole("tab", { name: /Cans/ }));
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText("Heineken Premium pilsener 0.0 6-pack")).toBeVisible();
    expect(within(panel).getByTitle("Alcohol-free")).toHaveTextContent("0.0");

    await userEvent.keyboard("{ArrowRight}");
    const bottles = screen.getByRole("tab", { name: /Bottles/ });
    expect(bottles).toHaveAttribute("aria-selected", "true");
    expect(bottles).toHaveFocus();
    expect(screen.getByText("No bottles on offer this week.")).toBeVisible();

    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: /Crates/ })).toHaveFocus();
  });

  it("explains a failing API", async () => {
    stubBeer(Response.json({ detail: "No deals cached yet." }, { status: 503 }));
    await openBeer();
    expect(await screen.findByRole("alert")).toHaveTextContent("No deals cached yet.");
  });

  it("goes back to the supermarkets", async () => {
    stubBeer(Response.json(BEER));
    await openBeer();
    await userEvent.click(screen.getByRole("link", { name: "Supermarkets" }));
    expect(await screen.findByRole("combobox", { name: "Postcode or place" })).toBeVisible();
  });
});
