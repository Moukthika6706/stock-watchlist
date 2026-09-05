import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api, { errorMessage } from '../api';
import AddStockPopover from '../components/AddStockPopover';
import AttentionHero from '../components/AttentionHero';
import TopNav from '../components/TopNav';
import WatchlistTable from '../components/WatchlistTable';
import { displayName } from '../lib/format';
import './WatchlistPage.css';

export default function WatchlistPage({ onSignOut }) {
  const [user, setUser] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [removingId, setRemovingId] = useState(null);
  const [notice, setNotice] = useState('');
  const inFlight = useRef(false);

  // GET /watchlist consumes the "since your last visit" diff on the server, so
  // it is called from exactly two places: this page mounting (which is also
  // what happens on login) and the explicit Refresh button. No polling, no
  // focus/visibility refetch, no refetch after add or remove. The inFlight ref
  // makes the button impossible to double-fire.
  const loadWatchlist = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.get('/watchlist');
      setItems(data.watchlist);
      setHasLoaded(true);
    } catch (err) {
      setError(errorMessage(err, 'Could not load your watchlist.'));
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, []);

  const loadUser = useCallback(async () => {
    try {
      const { data } = await api.get('/me');
      setUser(data);
    } catch {
      /* the avatar just shows a placeholder; auth failures are handled by the API layer */
    }
  }, []);

  // StrictMode mounts twice in development; without this guard the second GET
  // would immediately overwrite the baseline the first one just recorded.
  const mounted = useRef(false);
  useEffect(() => {
    if (mounted.current) return;
    mounted.current = true;
    loadUser();
    loadWatchlist();
  }, [loadUser, loadWatchlist]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(''), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  const watchedSymbols = useMemo(() => items.map((item) => item.symbol), [items]);

  // Sourced from the data feed itself, never from the client clock.
  const marketOpen = useMemo(() => {
    const flags = items.map((item) => item.latest?.is_market_open).filter((v) => v != null);
    return flags.length ? flags.some(Boolean) : null;
  }, [items]);

  // Most attention-worthy first, so the list reads top-down like the hero card.
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const filtered = needle
      ? items.filter(
          (item) =>
            item.symbol.toLowerCase().includes(needle) ||
            displayName(item.symbol, item.company_name).toLowerCase().includes(needle) ||
            (item.company_name || '').toLowerCase().includes(needle)
        )
      : items;
    return [...filtered].sort(
      (a, b) =>
        (b.latest?.attention_score ?? -1) - (a.latest?.attention_score ?? -1) || a.symbol.localeCompare(b.symbol)
    );
  }, [items, filter]);

  // Add: append the item the API returns instead of re-fetching, so the diffs
  // already on screen keep their baseline.
  async function addStock(symbol) {
    try {
      const { data } = await api.post('/watchlist', { symbol });
      setItems((current) => [data.item, ...current]);
      setNotice(`${symbol} added to your watchlist.`);
    } catch (err) {
      throw new Error(errorMessage(err, `Could not add ${symbol}.`));
    }
  }

  // Remove: drop the row locally; the digest and counts derive from `items`.
  async function removeStock(item) {
    setRemovingId(item.stock_id);
    try {
      await api.delete(`/watchlist/${item.stock_id}`);
      setItems((current) => current.filter((row) => row.stock_id !== item.stock_id));
      setNotice(`${item.symbol} removed from your watchlist.`);
    } catch (err) {
      setNotice(errorMessage(err, `Could not remove ${item.symbol}.`));
    } finally {
      setRemovingId(null);
    }
  }

  const refreshing = loading && hasLoaded;
  const showErrorPanel = Boolean(error) && !loading;

  return (
    <div className="page">
      <TopNav user={user} marketOpen={marketOpen} onSignOut={onSignOut} />

      <main className="content">
        <AttentionHero items={items} loading={loading} hasLoaded={hasLoaded} error={error} />

        <section className="card">
          <div className="toolbar">
            <label className="search">
              <svg className="search-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
                <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <input
                type="search"
                placeholder="Filter by company or ticker"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                aria-label="Filter by company or ticker"
              />
            </label>

            <div className="toolbar-right">
              {notice && (
                <span className="notice mono" role="status">
                  {notice}
                </span>
              )}
              <span className="count">
                {visible.length} of {items.length} {items.length === 1 ? 'stock' : 'stocks'}
              </span>
              <button
                type="button"
                className="refresh-btn"
                onClick={loadWatchlist}
                disabled={loading}
                aria-busy={loading}
                title="Check what changed since your last look"
              >
                <span className={`refresh-icon${loading ? ' is-spinning' : ''}`} aria-hidden="true">
                  ↻
                </span>
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
              <AddStockPopover watchedSymbols={watchedSymbols} onAdd={addStock} />
            </div>
          </div>

          {showErrorPanel && (
            <div className="load-error" role="alert">
              <p className="load-error-title">We couldn't load your watchlist.</p>
              <p className="load-error-detail mono">{error}</p>
              <button type="button" className="retry-btn" onClick={loadWatchlist}>
                Try again
              </button>
            </div>
          )}

          {!(showErrorPanel && !hasLoaded) && (
            <WatchlistTable
              items={visible}
              loading={loading}
              hasLoaded={hasLoaded}
              filter={filter}
              onRemove={removeStock}
              removingId={removingId}
            />
          )}
        </section>
      </main>
    </div>
  );
}
