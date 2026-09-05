import { attentionFor, significantItems, solidBadgeStyle } from '../lib/attention';
import { changeSentence, parseServerTime, visitLabel } from '../lib/format';

export default function AttentionHero({ items, loading, hasLoaded, error }) {
  if (loading && !hasLoaded) {
    return (
      <section className="hero" aria-busy="true">
        <div className="hero-left">
          <p className="hero-kicker mono">SINCE YOU LAST CHECKED</p>
          <h2 className="hero-title">Checking what changed…</h2>
        </div>
      </section>
    );
  }

  if (error && !hasLoaded) {
    return (
      <section className="hero">
        <div className="hero-left">
          <p className="hero-kicker mono">SINCE YOU LAST CHECKED</p>
          <h2 className="hero-title">We couldn't load your watchlist</h2>
          <p className="hero-sub">{error}</p>
        </div>
      </section>
    );
  }

  // N is defined once: stocks the backend did not classify as Stable, sorted by
  // score. The headline, the summary line and the row list all use this array.
  const significant = significantItems(items);
  const n = significant.length;
  const total = items.length;

  const lastVisitDates = items.map((item) => parseServerTime(item.last_seen?.at)).filter(Boolean);
  const lastVisit = lastVisitDates.length ? new Date(Math.max(...lastVisitDates)) : null;
  const visit = visitLabel(lastVisit);

  let title;
  let sub;
  if (total === 0) {
    title = 'Your watchlist is empty';
    sub = 'Add a stock and we will start tracking what changes between your visits.';
  } else {
    title = n === 0 ? 'Nothing significant since your last visit' : `${n} ${n === 1 ? 'stock needs' : 'stocks need'} your attention`;
    sub = visit
      ? `Last visit ${visit}. ${n} of ${total} ${total === 1 ? 'stock' : 'stocks'} moved enough to mention.`
      : `This is your first look at ${total === 1 ? 'this stock' : `these ${total} stocks`}. Come back later and we will show you what moved.`;
  }

  return (
    <section className={`hero${loading ? ' is-refreshing' : ''}`} aria-busy={loading}>
      <div className="hero-left">
        <p className="hero-kicker mono">SINCE YOU LAST CHECKED</p>
        <h2 className="hero-title">{title}</h2>
        <p className="hero-sub">{sub}</p>
      </div>

      {n > 0 && (
        <ul className="hero-list">
          {significant.map((item) => (
            <li className="hero-row" key={item.stock_id}>
              <span className="badge mono" style={solidBadgeStyle(item.latest.attention_category)}>
                {attentionFor(item).label.toUpperCase()}
              </span>
              <span className="hero-sentence">
                <strong>{item.symbol}</strong> {changeSentence(item)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
