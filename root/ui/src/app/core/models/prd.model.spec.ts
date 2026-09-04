import { renderPrdMarkdown } from './prd.model';

describe('renderPrdMarkdown', () => {
  it('renders a table whose last row lost its closing pipe instead of hanging', () => {
    const md = [
      '| Metric | Now | Target |',
      '|---|---|---|',
      '| Evening loss | 58,614 | lower',
      '',
      'Next paragraph.',
    ].join('\n');
    const html = renderPrdMarkdown(md);
    expect(html).toContain('<td>lower</td>');
    expect(html).toContain('<p>Next paragraph.</p>');
  });

  it('always makes progress on a line no block rule claims', () => {
    const html = renderPrdMarkdown('| lone pipe line without a header rule\n- item');
    expect(html).toContain('<li>item</li>');
  });
});
