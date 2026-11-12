import { UserManager, WebStorageStateStore, type User, type UserManagerSettings } from 'oidc-client-ts';

const enabled = ((import.meta.env.VITE_OIDC_ENABLED as string | undefined) ?? 'false').toLowerCase() === 'true';

function required(name: string, value: string | undefined): string {
  const normalized = value?.trim() ?? '';
  if (enabled && !normalized) throw new Error(`${name} is required when VITE_OIDC_ENABLED=true`);
  return normalized;
}

const authority = required('VITE_OIDC_AUTHORITY', import.meta.env.VITE_OIDC_AUTHORITY as string | undefined).replace(/\/$/, '');
const clientId = required('VITE_OIDC_CLIENT_ID', import.meta.env.VITE_OIDC_CLIENT_ID as string | undefined);
const redirectUri = required('VITE_OIDC_REDIRECT_URI', import.meta.env.VITE_OIDC_REDIRECT_URI as string | undefined);
const postLogoutRedirectUri = (import.meta.env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI as string | undefined)?.trim() || redirectUri;
const scope = (import.meta.env.VITE_OIDC_SCOPE as string | undefined)?.trim() || 'openid profile';

const settings: UserManagerSettings = {
  authority,
  client_id: clientId,
  redirect_uri: redirectUri,
  post_logout_redirect_uri: postLogoutRedirectUri,
  response_type: 'code',
  scope,
  loadUserInfo: false,
  automaticSilentRenew: true,
  monitorSession: true,
  // Persist bearer tokens only for the current browser session. sessionStorage still remains
  // script-readable, so CSP/XSS prevention remains mandatory.
  userStore: new WebStorageStateStore({ store: window.sessionStorage })
};

export const authEnabled = enabled;
export const userManager = enabled ? new UserManager(settings) : null;

export function isOidcCallbackUrl(): boolean {
  if (!enabled) return false;
  const params = new URLSearchParams(window.location.search);
  return params.has('code') && params.has('state');
}

export async function completeSignIn(): Promise<User | null> {
  if (!userManager || !isOidcCallbackUrl()) return userManager?.getUser() ?? null;
  const user = await userManager.signinRedirectCallback();
  window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
  return user;
}

export async function currentUser(): Promise<User | null> {
  if (!userManager) return null;
  return userManager.getUser();
}

export async function getAccessToken(): Promise<string | null> {
  if (!userManager) return null;
  let user = await userManager.getUser();
  if (!user || user.expired) {
    try {
      user = await userManager.signinSilent();
    } catch {
      return null;
    }
  }
  return user?.access_token || null;
}

export async function getAuthenticatedSubject(): Promise<string | null> {
  const user = await currentUser();
  const sub = user?.profile?.sub;
  return typeof sub === 'string' && sub.trim() ? sub.trim() : null;
}

export async function signIn(): Promise<void> {
  if (!userManager) return;
  await userManager.signinRedirect();
}

export async function signOut(): Promise<void> {
  if (!userManager) return;
  await userManager.signoutRedirect();
}
