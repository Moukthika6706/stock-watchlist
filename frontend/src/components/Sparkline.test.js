import { render } from '@testing-library/react';
import Sparkline from './Sparkline';

// The API returns however many snapshots exist, so very short arrays are normal
// right after a stock is added. None of these may throw or produce NaN.
describe('Sparkline', () => {
  test.each([
    ['no points', []],
    ['undefined points', undefined],
    ['one point', [100]],
    ['two points', [100, 101]],
    ['non-numeric noise', [null, undefined, 'x']],
  ])('renders with %s', (_label, points) => {
    const { container } = render(<Sparkline points={points} />);
    const d = container.querySelector('path').getAttribute('d');
    expect(d).toMatch(/^M/);
    expect(d).not.toMatch(/NaN|Infinity/);
  });

  test('a rising two-point series ends higher on screen than it starts', () => {
    const { container } = render(<Sparkline points={[10, 20]} width={100} height={40} />);
    const d = container.querySelector('path').getAttribute('d');
    const [, startY, endY] = d.match(/M[\d.]+,([\d.]+) L[\d.]+,([\d.]+)/).map(Number);
    expect(endY).toBeLessThan(startY); // SVG y grows downward
  });
});
