/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API path prefix, baked at build time. Must be a path — see client.ts. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
