/* Graphics for the Summary page.
 *
 * Each one restates figures the page already prints as a line of the return,
 * so every graphic has a table beside or under it and nothing is readable only
 * from a picture. Colour does one job at a time: one blue for what is being
 * measured, a neutral for what takes away from a total, and the page's own
 * status colours where a mark means agree or differ. A value is never shown by
 * colour alone -- it is printed next to its mark, and again on hover or focus.
 */

const SVGNS = 'http://www.w3.org/2000/svg';

/** el(), for the elements an <svg> needs. */
const svgEl = (tag, attrs = {}, ...kids) => {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
};

/** 0.2742 -> "27.4%"; trailing zeros dropped, so a slab rate reads "12.5%" or "30%". */
const pct = (n, digits = 1) => `${+(n * 100).toFixed(digits)}%`;

/** An amount short enough for an axis: 4L, 85.5L, 1.2Cr. */
const shortInr = (n) => {
  const a = Math.abs(n);
  if (a >= 1e7) return `${+(n / 1e7).toFixed(2)}Cr`;
  if (a >= 1e5) return `${+(n / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `${+(n / 1e3).toFixed(0)}K`;
  return String(n);
};

/* ---------------------------------------------------------------- tooltip */

/** The same details on hover and on keyboard focus. `build` returns the
 *  lines, value first: here the reader has the label and wants the number. */
function vizTip(node, build) {
  const tip = () => {
    let t = $('#viz-tip');
    if (!t) { t = el('div', { id: 'viz-tip', role: 'tooltip', hidden: '' }); document.body.append(t); }
    return t;
  };
  const place = (x, y) => {
    const t = tip();
    t.replaceChildren(...build().filter(Boolean));
    t.hidden = false;
    const r = t.getBoundingClientRect();
    t.style.left = `${Math.max(8, Math.min(x + 14, window.innerWidth - r.width - 8))}px`;
    t.style.top = `${y + 18 + r.height > window.innerHeight ? Math.max(8, y - r.height - 12) : y + 18}px`;
  };
  const hide = () => { tip().hidden = true; };
  node.addEventListener('pointerenter', (e) => place(e.clientX, e.clientY));
  node.addEventListener('pointermove', (e) => place(e.clientX, e.clientY));
  node.addEventListener('pointerleave', hide);
  node.addEventListener('focus', () => {
    const r = node.getBoundingClientRect();
    place(r.left + Math.min(r.width / 2, 120), r.bottom - 12);
  });
  node.addEventListener('blur', hide);
  return node;
}

/* ------------------------------------------------------------------ bars */

/** Amounts as bars from one baseline, each with its value printed beside it.
 *
 * rows: { label, value, sub?, share?, href?, tip?, tone? }. A negative value
 * runs the other way from the baseline in the neutral tone: it takes away
 * from the total, which is a direction and not a verdict.
 */
function barList(rows) {
  rows = rows.filter(Boolean);
  const pos = Math.max(0, ...rows.map((r) => r.value));
  const neg = Math.max(0, ...rows.map((r) => -r.value));
  const span = (pos + neg) || 1;
  const zero = neg / span * 100;
  return el('div', { class: 'bars', role: 'list' }, rows.map((r) => {
    const width = Math.abs(r.value) / span * 100;
    const bar = r.value ? el('span', {
      class: 'bar' + (r.value < 0 ? ' neg' : '') + (r.tone ? ` ${r.tone}` : ''),
      style: r.value > 0 ? `left:${zero}%;width:${width}%` : `right:${100 - zero}%;width:${width}%`,
    }) : null;
    const row = el(r.href ? 'a' : 'div', { class: 'bar-row', role: 'listitem', href: r.href || null,
                                           tabindex: r.href ? null : '0' },
      el('span', { class: 'bar-l' }, r.label, r.sub ? el('small', {}, r.sub) : null),
      el('span', { class: 'bar-t' },
        neg ? el('i', { class: 'bar-zero', style: `left:${zero}%` }) : null, bar),
      el('span', { class: 'bar-v' }, inr(r.value), r.share ? el('small', {}, r.share) : null));
    return vizTip(row, () => [
      el('b', {}, inr(r.value)), el('span', {}, r.label),
      r.tip ? el('span', { class: 'tip-sub' }, r.tip) : null]);
  }));
}

/* ----------------------------------------------------------- slab ladder */

/** Where the ordinary income sits on the slab ladder.
 *
 * Each column is one band: as wide as the income in it, as tall as its rate,
 * so its area is the tax it bears. One axis, one colour; the rate is printed
 * on the column where it fits and is always in the table under the chart.
 */
function slabChart(ladder) {
  const W = 560, H = 204, L = 36, R = 8, T = 20, B = 30;
  const income = ladder[ladder.length - 1].to;
  const yMax = Math.max(0.3, Math.ceil(Math.max(...ladder.map((b) => b.rate)) * 10 - 1e-9) / 10);
  const x = (v) => L + v / income * (W - L - R);
  const y = (r) => T + (1 - r / yMax) * (H - T - B);
  const out = [];

  for (let r = 0.1; r <= yMax + 1e-9; r += 0.1) {
    out.push(svgEl('line', { class: 'grid', x1: L, x2: W - R, y1: y(r), y2: y(r) }),
             svgEl('text', { class: 'tick', x: L - 6, y: y(r) + 4, 'text-anchor': 'end' }, pct(r, 0)));
  }

  for (const band of ladder) {
    // A 2px gap in the surface colour separates neighbours; no outlines.
    const x0 = x(band.from) + 1, x1 = Math.max(x0 + 1, x(band.to) - 1);
    const w = x1 - x0, top = y(band.rate), base = y(0), rad = Math.min(4, w / 2, (base - top) / 2);
    const says = [
      el('b', {}, `${inr(band.tax)} of tax`),
      el('span', {}, `${inr(band.amount)} of income at ${pct(band.rate, 2)}`),
      el('span', { class: 'tip-sub' }, `the part between ${inr(band.from)} and ${inr(band.to)}`)];
    const group = svgEl('g', { class: 'slab', tabindex: '0', role: 'img',
      'aria-label': `${inr(band.amount)} of income between ${inr(band.from)} and ${inr(band.to)}, `
                    + `taxed at ${pct(band.rate, 2)}: ${inr(band.tax)} of tax` },
      band.rate > 0 ? svgEl('path', { class: 'col', d:
        `M${x0},${base}V${top + rad}Q${x0},${top} ${x0 + rad},${top}H${x1 - rad}`
        + `Q${x1},${top} ${x1},${top + rad}V${base}Z` }) : null,
      // Neighbouring columns step up, so their labels sit at different
      // heights and a label a little wider than its column still has room.
      w >= 21 ? svgEl('text', { class: 'cap', x: (x0 + x1) / 2, y: top - 6, 'text-anchor': 'middle' },
                      pct(band.rate, 2)) : null,
      // Inside the column only where the words fit with room to spare.
      w >= 150 && base - top >= 56 ? [
        svgEl('text', { class: 'in', x: (x0 + x1) / 2, y: top + 26, 'text-anchor': 'middle' },
              `${inr(band.amount)} of income`),
        svgEl('text', { class: 'in strong', x: (x0 + x1) / 2, y: top + 44, 'text-anchor': 'middle' },
              `${inr(band.tax)} of tax`)] : null,
      // The whole height of the plot answers to the pointer, not only the ink.
      svgEl('rect', { class: 'hit', x: x(band.from), y: T, width: Math.max(2, x(band.to) - x(band.from)),
                      height: H - T - B }));
    out.push(vizTip(group, () => says));
  }
  out.push(svgEl('line', { class: 'axis', x1: L, x2: W - R, y1: y(0), y2: y(0) }));

  // Band boundaries along the bottom: the ends first, then whichever of the
  // rest have room, so two labels never run into each other.
  const marks = [0, ...ladder.map((b) => b.to)];
  const placed = [];
  const fits = (v) => placed.every((p) => Math.abs(x(p) - x(v)) >= 34);
  [0, income, ...marks.slice(1, -1)].forEach((v) => { if (fits(v)) placed.push(v); });
  for (const v of placed) {
    out.push(svgEl('text', { class: 'tick', x: x(v), y: H - 10,
                             'text-anchor': v === 0 ? 'start' : v === income ? 'end' : 'middle' },
                   v === 0 ? '₹0' : `₹${shortInr(v)}`));
  }
  return svgEl('svg', { class: 'slabs', viewBox: `0 0 ${W} ${H}`, role: 'group',
                        'aria-label': 'Ordinary income by slab band: width is the income in the band, height its rate' },
               out);
}

/* ------------------------------------------------------------------ meter */

/** What has been paid against what is due.
 *
 * The fill is the payments, side by side with a gap between them; the paler
 * track is what is still to pay. When more was paid than is due, a mark shows
 * where the tax ends and everything past it is the refund.
 */
function payMeter(parts, liability) {
  parts = parts.filter((p) => p.value > 0);
  const paid = parts.reduce((a, p) => a + p.value, 0);
  const due = Math.max(0, liability - paid);
  const refund = Math.max(0, paid - liability);
  const scale = Math.max(liability, paid) || 1;
  const of = (v) => (liability ? `${pct(v / liability)} of the tax` : '');

  const meter = el('div', { class: 'meter', role: 'img',
    'aria-label': `${inr(paid)} paid against ${inr(liability)} of tax` });
  const legend = el('div', { class: 'legend' });
  const add = (label, value, cls, href) => {
    const seg = el('span', { class: 'meter-seg' + (cls ? ` ${cls}` : ''), style: `flex:${value} 1 0` });
    vizTip(seg, () => [el('b', {}, inr(value)), el('span', {}, label), el('span', { class: 'tip-sub' }, of(value))]);
    const row = el(href ? 'a' : 'div', { class: 'legend-row', href: href || null },
      el('i', { class: 'sw' + (cls ? ` ${cls}` : '') }), el('span', {}, label),
      el('b', {}, inr(value)), el('small', {}, of(value)));
    // Every payment is the same blue, so pointing at a row shows which piece it is.
    row.addEventListener('pointerenter', () => { meter.classList.add('has-hot'); seg.classList.add('hot'); });
    row.addEventListener('pointerleave', () => { meter.classList.remove('has-hot'); seg.classList.remove('hot'); });
    meter.append(seg);
    legend.append(row);
  };
  parts.forEach((p) => add(p.label, p.value, '', p.href));
  if (due) add('Still to pay', due, 'rest', '#summary');
  if (refund) {
    meter.append(el('i', { class: 'meter-mark', style: `left:${liability / scale * 100}%` }));
    legend.append(el('div', { class: 'legend-row' }, el('i', { class: 'sw mark' }),
      el('span', {}, 'Paid beyond the tax: refund'), el('b', {}, inr(refund)), el('small', {}, '')));
  }
  return el('div', {}, el('div', { class: 'meter-wrap' }, meter), legend);
}

/** A fraction done, as a slim bar. The words beside it carry the numbers. */
const miniMeter = (done, total) => el('span', { class: 'mini-meter', 'aria-hidden': 'true' },
  el('i', { style: `width:${total ? Math.max(0, Math.min(100, done / total * 100)) : 0}%` }));

/** Counts by outcome as one bar, each outcome named and counted under it. */
function statusBar(parts) {
  parts = parts.filter((p) => p.value > 0);
  if (!parts.length) return null;
  return el('div', { class: 'status-bar' },
    el('div', { class: 'meter', role: 'img',
                'aria-label': parts.map((p) => `${p.value} ${p.label}`).join(', ') },
      parts.map((p) => vizTip(el('span', { class: `meter-seg ${p.tone}`, style: `flex:${p.value} 1 0` }),
        () => [el('b', {}, String(p.value)), el('span', {}, p.label)]))),
    el('div', { class: 'status-key' }, parts.map((p) =>
      el('span', {}, el('i', { class: `sw ${p.tone}` }), el('b', {}, String(p.value)), ` ${p.label}`))));
}

/* ------------------------------------------------------------------ tiles */

/** One figure worth knowing, with what it is a figure of. */
const statTile = (label, value, sub, extra = null) => el('div', { class: 'tile' },
  el('div', { class: 'tile-l' }, label),
  el('div', { class: 'tile-v' }, value),
  sub ? el('div', { class: 'tile-s' }, sub) : null, extra);
