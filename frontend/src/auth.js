// The JWT lives in localStorage so a session survives reloads and browser restarts.
// The watchlist itself is server-side, so signing in on another device shows the same list.
const TOKEN_KEY = 'stocksense.token';

export const SIGNOUT_EVENT = 'stocksense:signout';

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* private mode: the session simply will not persist */
  }
}

export function clearToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function decodeTokenPayload(token) {
  if (typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

// Cheap client-side sanity check so a missing, malformed or expired token sends
// the user to login without firing a request that is bound to fail. The server
// still verifies the signature on every protected call.
export function hasUsableToken() {
  const payload = decodeTokenPayload(getToken());
  if (!payload || payload.sub == null) return false;
  if (typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now()) return false;
  return true;
}

// The one place auth failure is handled: drop the token and tell the app shell
// to show the login screen. Used by the API interceptor, app boot, and sign-out.
export function handleAuthFailure() {
  clearToken();
  window.dispatchEvent(new Event(SIGNOUT_EVENT));
}
