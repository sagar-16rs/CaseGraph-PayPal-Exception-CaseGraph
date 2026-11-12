import { useEffect, useState, type ReactNode } from 'react';
import type { User } from 'oidc-client-ts';
import { authEnabled, completeSignIn, currentUser, signIn, signOut, userManager } from './session';

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(!authEnabled);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authEnabled || !userManager) return;
    const manager = userManager;
    let alive = true;
    const refresh = async () => {
      try {
        const next = await completeSignIn();
        const resolved = next ?? await currentUser();
        if (alive) setUser(resolved && !resolved.expired ? resolved : null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Authentication failed.');
      } finally {
        if (alive) setReady(true);
      }
    };
    const onLoaded = (next: User) => { if (alive) setUser(next); };
    const onUnloaded = () => { if (alive) setUser(null); };
    const onExpired = () => { if (alive) setUser(null); };
    manager.events.addUserLoaded(onLoaded);
    manager.events.addUserUnloaded(onUnloaded);
    manager.events.addUserSignedOut(onUnloaded);
    manager.events.addAccessTokenExpired(onExpired);
    void refresh();
    return () => {
      alive = false;
      manager.events.removeUserLoaded(onLoaded);
      manager.events.removeUserUnloaded(onUnloaded);
      manager.events.removeUserSignedOut(onUnloaded);
      manager.events.removeAccessTokenExpired(onExpired);
    };
  }, []);

  if (!authEnabled) return <>{children}</>;
  if (!ready) return <div className="empty-state"><strong>Signing in…</strong></div>;
  if (!user) {
    return (
      <div className="empty-state">
        <strong>Authentication required</strong>
        <span>{error ?? 'Sign in with your organization identity to access CaseGraph.'}</span>
        <button className="button button-primary" type="button" onClick={() => void signIn()}>Sign in</button>
      </div>
    );
  }
  return (
    <>
      <div className="auth-session-bar">
        <span>Signed in as {String(user.profile.email ?? user.profile.preferred_username ?? user.profile.sub)}</span>
        <button className="button button-secondary" type="button" onClick={() => void signOut()}>Sign out</button>
      </div>
      {children}
    </>
  );
}
