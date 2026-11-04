import "@testing-library/jest-dom/vitest"; // matchers such as toBeInTheDocument()
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library unmounts after each test by itself only when the test runner's
// functions are globals; Vitest keeps them as imports, so do it here.
afterEach(cleanup);
