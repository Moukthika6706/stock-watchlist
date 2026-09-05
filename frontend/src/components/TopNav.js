import { useEffect, useRef, useState } from 'react';
import GrowwLogo from './GrowwLogo';

const PRIMARY_TABS = ['Stocks', 'F&O', 'Mutual Funds'];
const SECONDARY_TABS = ['Explore', 'Holdings', 'Positions', 'Orders', 'Watchlist'];

function userInitials(user) {
  const source = user?.name || user?.email || '';
  const parts = source.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return source.slice(0, 2).toUpperCase() || '··';
}

export default function TopNav({ user, marketOpen, onSignOut }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    function onDocumentClick(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', onDocumentClick);
    return () => document.removeEventListener('mousedown', onDocumentClick);
  }, [menuOpen]);

  return (
    <header className="topbar">
      <div className="topbar-row">
        <div className="brand">
          <GrowwLogo size={52} className="brand-logo" />
          <nav className="primary-tabs" aria-label="Products">
            {PRIMARY_TABS.map((tab) => (
              <span key={tab} className={tab === 'Stocks' ? 'is-active' : ''} aria-current={tab === 'Stocks' ? 'page' : undefined}>
                {tab}
              </span>
            ))}
          </nav>
        </div>

        <div className="topbar-right">
          {/* Sourced from latest.is_market_open on the watched stocks; hidden until there is data to source it from. */}
          {marketOpen != null && (
            <span className={`market mono ${marketOpen ? 'is-open' : 'is-closed'}`}>
              <span className="market-dot" aria-hidden="true" />
              {marketOpen ? 'Market open' : 'Market closed'}
            </span>
          )}

          <div className="avatar-wrap" ref={menuRef}>
            <button
              type="button"
              className="avatar"
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              title={user?.name || 'Account'}
            >
              {userInitials(user)}
            </button>
            {menuOpen && (
              <div className="avatar-menu" role="menu">
                <p className="avatar-menu-name">{user?.name || 'Signed in'}</p>
                <p className="avatar-menu-email mono">{user?.email || ''}</p>
                <button type="button" role="menuitem" className="avatar-menu-signout" onClick={onSignOut}>
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="topbar-row subbar-row">
        <nav className="secondary-tabs" aria-label="Sections">
          {SECONDARY_TABS.map((tab) => (
            <span key={tab} className={tab === 'Watchlist' ? 'is-active' : ''} aria-current={tab === 'Watchlist' ? 'page' : undefined}>
              {tab}
            </span>
          ))}
        </nav>
        <button type="button" className="terminal-btn" title="Terminal">
          <span className="terminal-icon" aria-hidden="true">
            ||
          </span>
          Terminal
        </button>
      </div>
    </header>
  );
}
