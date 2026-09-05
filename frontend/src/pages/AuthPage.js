import { useState } from 'react';
import api, { errorMessage } from '../api';
import { setToken } from '../auth';
import GrowwLogo from '../components/GrowwLogo';
import './AuthPage.css';

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const isSignup = mode === 'signup';

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (isSignup && !name.trim()) {
      setError('Please enter your name.'); // native `required` catches empty; this catches whitespace
      return;
    }
    setBusy(true);
    try {
      if (isSignup) {
        await api.post('/signup', { name, email, password });
      }
      const { data } = await api.post('/login', { email, password });
      setToken(data.access_token);
      onAuthenticated(data.access_token);
    } catch (err) {
      setError(errorMessage(err, isSignup ? 'Could not create your account.' : 'Could not sign you in.'));
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next) {
    setMode(next);
    setError('');
  }

  return (
    <div className="auth">
      <aside className="auth-hero">
        <div className="auth-brand">
          <span className="auth-brand-mark">
            <GrowwLogo size={28} />
          </span>
          <span className="auth-brand-name">Stock Sense</span>
        </div>
        <h1 className="auth-tagline">
          Know what moved
          <br />
          since you last looked.
        </h1>
      </aside>

      <main className="auth-panel">
        <form className="auth-form" onSubmit={submit}>
          <h2 className="auth-title">{isSignup ? 'Create your account' : 'Welcome back'}</h2>

          {isSignup && (
            <label className="auth-field">
              <span className="sr-only">Your name</span>
              <input
                type="text"
                name="name"
                placeholder="Your name"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
          )}

          <label className="auth-field">
            <span className="sr-only">Your email address</span>
            <input
              type="email"
              name="email"
              placeholder="Your email address"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>

          <label className="auth-field">
            <span className="sr-only">Password</span>
            <input
              type="password"
              name="password"
              placeholder="Password"
              autoComplete={isSignup ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? 'Please wait…' : isSignup ? 'Create account' : 'Continue'}
          </button>

          <p className="auth-legal">
            By proceeding, I agree to <a href="#terms">T&amp;C</a> &amp; <a href="#privacy">Privacy Policy</a>
          </p>

          <p className="auth-switch">
            {isSignup ? (
              <>
                Already have an account?{' '}
                <button type="button" onClick={() => switchMode('login')}>
                  Sign in
                </button>
              </>
            ) : (
              <>
                New here?{' '}
                <button type="button" onClick={() => switchMode('signup')}>
                  Create an account
                </button>
              </>
            )}
          </p>
        </form>
      </main>
    </div>
  );
}
