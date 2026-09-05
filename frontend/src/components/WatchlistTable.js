import { Fragment, useEffect, useState } from 'react';
import { attentionFor } from '../lib/attention';
import {
  agoFromDate,
  agoFromSeconds,
  avatarColors,
  displayName,
  initials,
  money,
  parseServerTime,
  signedPct,
  trendColor,
} from '../lib/format';
import AttentionPill from './AttentionPill';
import RangeBar from './RangeBar';
import Sparkline from './Sparkline';

export default function WatchlistTable({ items, loading, hasLoaded, filter, onRemove, removingId }) {
  const [expandedId, setExpandedId] = useState(null);

  // Collapse the "why this score" panel if its row is removed (or filtered out).
  useEffect(() => {
    if (expandedId != null && !items.some((item) => item.stock_id === expandedId)) {
      setExpandedId(null);
    }
  }, [items, expandedId]);

  if (loading && !hasLoaded) {
    return <p className="table-empty mono">Loading your watchlist…</p>;
  }

  if (items.length === 0) {
    return (
      <p className="table-empty">
        {filter ? 'No stocks match that filter.' : 'Nothing here yet. Use “Add stock” above to add your first stock.'}
      </p>
    );
  }

  return (
    <div className={`table-wrap${loading ? ' is-refreshing' : ''}`} aria-busy={loading}>
      <table className="wl">
        <thead>
          <tr>
            <th className="col-company">Company</th>
            <th className="col-trend">Trend</th>
            <th className="col-price num">Price</th>
            <th className="col-change num">Change since last seen</th>
            <th className="col-attention">Attention</th>
            <th className="col-range">52W range</th>
            <th className="col-updated num">Updated</th>
            <th className="col-actions">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const latest = item.latest;
            const pct = latest?.change_since_last_visit_pct;
            const lastSeenAt = parseServerTime(item.last_seen?.at);
            const expanded = expandedId === item.stock_id;
            const changeClass = pct == null || Math.abs(pct) < 0.05 ? 'flat' : pct > 0 ? 'up' : 'down';
            const removing = removingId === item.stock_id;

            return (
              <Fragment key={item.stock_id}>
                <tr
                  className={`wl-row${expanded ? ' is-expanded' : ''}`}
                  onClick={() => latest && setExpandedId(expanded ? null : item.stock_id)}
                  aria-expanded={expanded}
                >
                  <td className="col-company">
                    <div className="company">
                      <span className="company-avatar mono" style={avatarColors(item.symbol)}>
                        {initials(item.symbol)}
                      </span>
                      <div className="company-text">
                        <span className="company-name">{displayName(item.symbol, item.company_name)}</span>
                        <span className="company-symbol mono">{item.symbol}</span>
                      </div>
                    </div>
                  </td>

                  <td className="col-trend">
                    {latest ? <Sparkline points={latest.sparkline} color={trendColor(item)} /> : <span className="dim">—</span>}
                  </td>

                  <td className="col-price num mono">{latest ? money(latest.price) : '—'}</td>

                  <td className="col-change num">
                    {pct == null ? (
                      <span className="change mono change-flat">First view</span>
                    ) : (
                      <span className={`change mono change-${changeClass}`}>{signedPct(pct)}</span>
                    )}
                    {item.last_seen && (
                      <span className="change-sub mono">
                        last seen {money(item.last_seen.price)} · {agoFromDate(lastSeenAt)}
                      </span>
                    )}
                  </td>

                  <td className="col-attention">{latest ? <AttentionPill item={item} /> : <span className="dim">—</span>}</td>

                  <td className="col-range">
                    {latest ? <RangeBar low={latest.week52_low} high={latest.week52_high} price={latest.price} /> : <span className="dim">—</span>}
                  </td>

                  <td className="col-updated num mono">{latest ? `updated ${agoFromSeconds(latest.age_seconds)}` : 'no data yet'}</td>

                  <td className="col-actions">
                    <button
                      type="button"
                      className="row-remove mono"
                      aria-label={`Remove ${item.symbol} from watchlist`}
                      title="Remove from watchlist"
                      disabled={removing}
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemove(item);
                      }}
                    >
                      {removing ? 'Removing…' : 'Remove'}
                    </button>
                  </td>
                </tr>

                {expanded && latest && (
                  <tr className="wl-details">
                    <td colSpan={8}>
                      <div className="details" style={{ borderLeftColor: attentionFor(item).color }}>
                        <p className="details-title">
                          Why {item.symbol} scores {latest.attention_score} / 100
                          <span className="details-cat mono"> · {latest.attention_category}</span>
                        </p>
                        <ul className="details-reasons">
                          {latest.score_breakdown.reasons.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                        <p className="details-formula mono">
                          score = min(40, 40 × |% change since last visit|) + 30 × volume spike + 30 × 52-week milestone ·
                          {' '}
                          {latest.score_breakdown.price_change_points} + {latest.score_breakdown.volume_points} +{' '}
                          {latest.score_breakdown.milestone_points} = {latest.attention_score}
                        </p>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
