/**
 * The page's only connection to the backend: `POST /api/rank`.
 *
 * The types come from `schema.d.ts`, which `npm run gen:api` generates from the
 * API's OpenAPI schema. They are never written by hand, so a change to the API's
 * request or response models shows up here as a type error.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];
export type RankRequest = Schemas["RankRequest"];
export type RankResponse = Schemas["RankResponse"];
export type RankedStore = Schemas["RankedStore"];
export type Deal = Schemas["DealOut"];
export type Diet = Schemas["Diet"];
export type Cuisine = Schemas["Cuisine"];

/** A failed API call, with a message that can be shown to the user as is. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const START_THE_API = "Is the API running? Start it with `uv run koopjeskompas serve`.";

export async function rankStores(request: RankRequest): Promise<RankResponse> {
  const body = JSON.stringify(request);
  let response: Response;
  try {
    response = await fetch("/api/rank", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // On AWS, CloudFront signs each request to the API's Lambda function, but
        // leaves hashing a POST body to the sender. Without the hash, Lambda refuses
        // the request. Locally the header is passed on and ignored.
        "x-amz-content-sha256": await sha256Hex(body),
      },
      body,
    });
  } catch {
    // fetch only rejects when there is no HTTP response at all.
    throw new ApiError(0, `Can't reach the API. ${START_THE_API}`);
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  // Trusted rather than validated: the API's response model guarantees this shape.
  return (await response.json()) as RankResponse;
}

/** The SHA-256 of a text's UTF-8 bytes, as lowercase hex. */
export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** FastAPI's reason for an error, from the JSON body's `detail`. */
async function errorMessage(response: Response): Promise<string> {
  const body: unknown = await response.json().catch(() => undefined);
  const detail = (body as { detail?: unknown } | undefined)?.detail;

  // An HTTPException, such as the 503 when no deals are cached, has a text detail.
  if (typeof detail === "string") {
    return detail;
  }
  // A 422 lists the fields that failed validation.
  if (response.status === 422 && Array.isArray(detail)) {
    const errors = detail as NonNullable<Schemas["HTTPValidationError"]["detail"]>;
    return errors
      .map(({ loc, msg }) => `${loc.filter((part) => part !== "body").join(".")}: ${msg}`)
      .join("; ");
  }
  return `The API answered ${response.status} ${response.statusText}. ${START_THE_API}`;
}
