/// <reference types="vite/client" />
declare module '*.glb?url' {
  const url: string
  export default url
}
interface ImportMetaEnv {
  readonly VITE_API?: 'mock' | 'live'
  readonly VITE_API_BASE?: string
}
