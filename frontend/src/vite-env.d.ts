/// <reference types="vite/client" />

// The build settings the page reads (`import.meta.env`), typed. Only variables
// starting with VITE_ reach the browser code, so no secret ends up in the page.
interface ImportMetaEnv {
  /** The API's address when it isn't on the page's own domain; see api/client.ts. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
