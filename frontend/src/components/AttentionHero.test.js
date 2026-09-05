import { render, screen } from '@testing-library/react';
import AttentionHero from './AttentionHero';
import { ATTENTION } from '../lib/attention';

function item(symbol, category, score, extra = {}) {
  return {
    stock_id: symbol.charCodeAt(0),
    symbol,
    company_name: symbol,
    last_seen: { price: 100, volume: 1, at: '2026-09-05T15:00:00' },
    latest: {
      price: 101,
      change_since_last_visit_pct: 1,
      volume_ratio: 1.2,
      milestones: [],
      attention_category: category,
      attention_score: score,
      ...extra,
    },
  };
}

const loaded = { loading: false, hasLoaded: true, error: '' };

describe('AttentionHero digest consistency', () => {
  test('headline, summary and row list all use the same N (non-Stable count), rows sorted by score', () => {
    const items = [
      item('AAPL', 'Stable', 0),
      item('TSLA', 'Monitor', 40),
      item('NVDA', 'Immediate attention', 90),
      item('AMZN', 'Important', 70),
    ];
    render(<AttentionHero items={items} {...loaded} />);
    expect(screen.getByRole('heading')).toHaveTextContent('3 stocks need your attention');
    expect(screen.getByText(/3 of 4 stocks moved enough to mention/)).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows.map((row) => row.querySelector('strong').textContent)).toEqual(['NVDA', 'AMZN', 'TSLA']);
  });

  test('badge labels come from the shared attention module', () => {
    render(<AttentionHero items={[item('NVDA', 'Immediate attention', 90)]} {...loaded} />);
    expect(screen.getByText(ATTENTION['Immediate attention'].label.toUpperCase())).toBeInTheDocument();
    expect(screen.getByRole('heading')).toHaveTextContent('1 stock needs your attention');
  });

  test('N of zero renders the calm state with no rows', () => {
    render(<AttentionHero items={[item('AAPL', 'Stable', 0), item('MSFT', 'Stable', 10)]} {...loaded} />);
    expect(screen.getByRole('heading')).toHaveTextContent('Nothing significant since your last visit');
    expect(screen.getByText(/0 of 2 stocks moved enough to mention/)).toBeInTheDocument();
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });

  test('empty watchlist prompts to add a stock', () => {
    render(<AttentionHero items={[]} {...loaded} />);
    expect(screen.getByRole('heading')).toHaveTextContent('Your watchlist is empty');
  });

  test('summary timestamp is the most recent last_seen across stocks', () => {
    const items = [
      item('AAPL', 'Stable', 0),
      { ...item('MSFT', 'Stable', 0), last_seen: { price: 1, volume: 1, at: '2026-09-05T16:10:00' } },
    ];
    render(<AttentionHero items={items} {...loaded} />);
    expect(screen.getByText(/Last visit .*4:10 PM/)).toBeInTheDocument();
  });
});
