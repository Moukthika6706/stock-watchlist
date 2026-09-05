import { useEffect, useState } from 'react';
import { SIGNOUT_EVENT, clearToken, getToken, handleAuthFailure, hasUsableToken } from './auth';
import AuthPage from './pages/AuthPage';
import WatchlistPage from './pages/WatchlistPage';

// Two screens, gated by whether a usable JWT is stored: no router needed.
export default function App() {
  const [token, setTokenState] = useState(() => {
    if (hasUsableToken()) return getToken();
    clearToken(); // anything malformed or expired left in storage goes straight to login
    return null;
  });

  useEffect(() => {
    const onSignOut = () => setTokenState(null);
    window.addEventListener(SIGNOUT_EVENT, onSignOut);
    return () => window.removeEventListener(SIGNOUT_EVENT, onSignOut);
  }, []);

  if (!token) {
    return <AuthPage onAuthenticated={(newToken) => setTokenState(newToken)} />;
  }

  return <WatchlistPage onSignOut={handleAuthFailure} />;
}
