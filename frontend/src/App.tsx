import { BeerPage } from "./pages/BeerPage";
import { RankPage } from "./pages/RankPage";
import { BEER_HASH, useRoute } from "./route";

/** The page's shell: the name, the two sections, and whichever one is chosen. */
export function App() {
  const route = useRoute();
  return (
    <main className="page">
      <header className="masthead">
        <h1>
          <span aria-hidden="true">🧭</span> Koopjeskompas
        </h1>
        <nav aria-label="Sections" className="sections">
          <a href="#/" aria-current={route === "stores" ? "page" : undefined}>
            Supermarkets
          </a>
          <a href={BEER_HASH} aria-current={route === "beer" ? "page" : undefined}>
            Beer
          </a>
        </nav>
      </header>
      {route === "beer" ? <BeerPage /> : <RankPage />}
    </main>
  );
}
