/// <reference types="vite/client" />
declare module '*.glb?url' {
  const url: string
  export default url
}
/** http://<this computer's Wi-Fi address>:5173, or null with no network (set by scan-upload.ts). */
declare const __LAN_ORIGIN__: string | null
/** Changes every time the dev server starts; the phone upload page must present it. */
declare const __UPLOAD_TOKEN__: string

interface ImportMetaEnv {
  readonly VITE_API?: 'mock' | 'live'
  readonly VITE_API_BASE?: string
}
