declare module 'react' { export type ReactNode = any; export function useEffect(fn:any,deps?:any[]):void; export function useMemo<T>(fn:()=>T,deps?:any[]):T; export function useState<T>(v:T):[T,(v:any)=>void]; const React:any; export default React; }
declare module 'react-dom/client' { const ReactDOM:any; export default ReactDOM; }
declare module 'react/jsx-runtime' { export const jsx:any; export const jsxs:any; export const Fragment:any; }
declare module 'oidc-client-ts' { export interface User { expired?:boolean; access_token?:string; profile:any } export interface UserManagerSettings {[k:string]:any} export class WebStorageStateStore { constructor(x:any) } export class UserManager { constructor(s:any); getUser():Promise<User|null>; signinRedirectCallback():Promise<User>; signinSilent():Promise<User>; signinRedirect():Promise<void>; signoutRedirect():Promise<void>; events:any } }
interface ImportMeta { env: Record<string, any> }

declare namespace JSX {
  interface IntrinsicElements { [elemName: string]: any }
}
