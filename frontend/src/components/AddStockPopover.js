import { useEffect, useRef, useState } from 'react';
import { ALLOWED_SYMBOLS, displayName } from '../lib/format';

// "+ Add stock" button plus a popover listing the six supported tickers.
// Tickers already on the watchlist are shown but disabled.
export default function AddStockPopover({ watchedSymbols, onAdd }) {
  const [open, setOpen] = useState(false);
  const [busySymbol, setBusySymbol] = useState(null);
  const [error, setError] = useState('');
  const rootRef = useRef(null);

  const exhausted = ALLOWED_SYMBOLS.every((symbol) => watchedSymbols.includes(symbol));

  useEffect(() => {
    if (!open) return undefined;
    function onDocumentClick(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocumentClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocumentClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  async function pick(symbol) {
    setError('');
    setBusySymbol(symbol);
    try {
      await onAdd(symbol);
      setOpen(false);
    } catch (err) {
      setError(err.message || 'Could not add that stock.'); // includes the API's 409 "already on your watchlist"
    } finally {
      setBusySymbol(null);
    }
  }

  return (
    <div className="add-stock" ref={rootRef}>
      <button
        type="button"
        className={`add-btn${exhausted ? ' add-btn-exhausted' : ''}`}
        onClick={() => !exhausted && setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        title={exhausted ? 'All supported tickers are already on your watchlist' : 'Add a stock to your watchlist'}
      >
        <span className="add-btn-plus" aria-hidden="true">
          +
        </span>
        Add stock
      </button>

      {open && (
        <div className="add-pop" role="listbox" aria-label="Available stocks">
          <p className="add-pop-title mono">SUPPORTED TICKERS</p>
          {ALLOWED_SYMBOLS.map((symbol) => {
            const added = watchedSymbols.includes(symbol);
            return (
              <button
                key={symbol}
                type="button"
                role="option"
                aria-selected="false"
                aria-disabled={added}
                className={`add-pop-row${added ? ' is-added' : ''}`}
                disabled={added || busySymbol !== null}
                onClick={() => pick(symbol)}
              >
                <span className="add-pop-symbol mono">{symbol}</span>
                <span className="add-pop-name">{displayName(symbol)}</span>
                <span className="add-pop-action mono">{busySymbol === symbol ? 'adding…' : added ? 'added' : 'add'}</span>
              </button>
            );
          })}
          {error && (
            <p className="add-pop-error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
