// Presentation helpers: formatting, relative time, and the templated summary
// sentence. No AI-generated text anywhere; every sentence is assembled from
// the numbers the API already returns.

export const ALLOWED_SYMBOLS = ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'NVDA']; // mirrors the backend whitelist

const DISPLAY_NAMES = {
  AAPL: 'Apple',
  TSLA: 'Tesla',
  MSFT: 'Microsoft',
  GOOGL: 'Alphabet',
  AMZN: 'Amazon',
  NVDA: 'NVIDIA',
};

// Attention categories, labels and colours live in ./attention.js.

export function displayName(symbol, companyName) {
  if (DISPLAY_NAMES[symbol]) return DISPLAY_NAMES[symbol];
  return (companyName || symbol)
    .replace(/,?\s+(Inc\.?|Corporation|Corp\.?|Common Stock|Class [A-C]|Ltd\.?|plc)\b/gi, '')
    .trim();
}

export function initials(symbol) {
  return (symbol || '??').slice(0, 2).toUpperCase();
}

const AVATAR_PALETTE = [
  ['#fde2e2', '#b42318'],
  ['#eee4fb', '#5b21b6'],
  ['#fdebd3', '#9a3412'],
  ['#ddebfb', '#1d4ed8'],
  ['#d8f3ec', '#0f766e'],
  ['#e4f2da', '#3f6212'],
];

const AVATAR_FIXED = { TSLA: 0, NVDA: 1, AMZN: 2, AAPL: 3, MSFT: 4, GOOGL: 5 };

export function avatarColors(symbol) {
  let index = AVATAR_FIXED[symbol];
  if (index === undefined) {
    index = [...(symbol || '')].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % AVATAR_PALETTE.length;
  }
  const [bg, fg] = AVATAR_PALETTE[index];
  return { background: bg, color: fg };
}

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

export function money(value) {
  return value == null ? '—' : usd.format(value);
}

export function signedPct(value, digits = 1) {
  if (value == null) return '—';
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function compact(value) {
  if (value == null) return '—';
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1).replace(/\.0$/, '')}k`;
  return Math.round(value).toString();
}

// Flask returns naive ISO strings in the server's local time; the browser runs
// on the same machine for the demo, so parsing them as local time is correct.
export function parseServerTime(iso) {
  return iso ? new Date(iso) : null;
}

export function agoFromSeconds(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function agoFromDate(date, now = new Date()) {
  if (!date) return '—';
  return agoFromSeconds(Math.max(0, (now - date) / 1000));
}

export function visitLabel(date, now = new Date()) {
  if (!date) return null;
  const time = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return `today, ${time}`;
  if (date.toDateString() === yesterday.toDateString()) return `yesterday, ${time}`;
  return `on ${date.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}, ${time}`;
}

// "is up 5.0% since your last visit, on 1.7x normal volume and trading near its 52-week high."
// Returned without the ticker so the caller can render the ticker in bold.
export function changeSentence(item) {
  const latest = item.latest || {};
  const pct = latest.change_since_last_visit_pct;
  const ratio = latest.volume_ratio;
  const milestones = latest.milestones || [];

  const clauses = [];
  if (ratio != null) clauses.push(`on ${ratio.toFixed(1)}x normal volume`);
  if (milestones.includes('near_52w_high')) clauses.push('trading near its 52-week high');
  else if (milestones.includes('near_52w_low')) clauses.push('trading near its 52-week low');

  let head;
  if (pct == null) head = `is trading at ${money(latest.price)}`;
  else if (Math.abs(pct) < 0.05) head = 'is flat since your last visit';
  else head = `is ${pct > 0 ? 'up' : 'down'} ${Math.abs(pct).toFixed(1)}% since your last visit`;

  return clauses.length ? `${head}, ${clauses.join(' and ')}.` : `${head}.`;
}

export function trendColor(item) {
  const latest = item.latest || {};
  const pct = latest.change_since_last_visit_pct;
  if (pct != null && Math.abs(pct) >= 0.05) return pct > 0 ? 'var(--up)' : 'var(--down)';
  const spark = latest.sparkline || [];
  if (spark.length >= 2 && spark[spark.length - 1] < spark[0]) return 'var(--down)';
  return 'var(--up)';
}
