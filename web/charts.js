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

/** The one tooltip every graphic shares, shown near (x, y) in the window. */
function showTip(lines, x, y) {
  let t = $('#viz-tip');
  if (!t) { t = el('div', { id: 'viz-tip', role: 'tooltip', hidden: '' }); document.body.append(t); }
  t.replaceChildren(...lines.filter(Boolean));
  t.hidden = false;
  const r = t.getBoundingClientRect();
  t.style.left = `${Math.max(8, Math.min(x + 14, window.innerWidth - r.width - 8))}px`;
  t.style.top = `${y + 18 + r.height > window.innerHeight ? Math.max(8, y - r.height - 12) : y + 18}px`;
}

function hideTip() {
  const t = $('#viz-tip');
  if (t) t.hidden = true;
}

/** The same details on hover and on keyboard focus. `build` returns the
 *  lines, value first: here the reader has the label and wants the number. */
function vizTip(node, build) {
  const place = (x, y) => showTip(build(), x, y);
  const hide = hideTip;
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

/* ------------------------------------------------------------- tax share */

/** Each point of a tax curve with what is kept and the tax in all. */
function taxPoints(curve) {
  return curve.income.map((income, i) => {
    const tax = curve.tax[i], sur = curve.surcharge[i], cess = curve.cess[i];
    const total = tax + sur + cess;
    return { income, tax, sur, cess, total, kept: income - total };
  });
}

/** Round steps for a rupee axis: no more than six of them up to `max`. */
function rupeeTicks(max) {
  const step = [100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000, 25_000_000]
    .find((s) => max / s <= 6) || 50_000_000;
  const top = Math.max(step, Math.ceil(max / step) * step);
  return Array.from({ length: top / step + 1 }, (_, i) => i * step);
}

/** The frame both tax charts share: bands stacked over income.
 *
 * o.pts      the points, each with an income
 * o.bands    bottom to top: { cls, h(p), gap } -- each band's own height at p,
 *            and the width of the surface line above it (2, or 1 where the
 *            bands are thin enough that 2 would hide them)
 * o.ticks    the y-axis values, from 0 to the top; o.tickLabel names each
 * o.marks    incomes where the rules change: { at, label }
 * o.edge     draw the top of the stack as a hairline, when it means something
 * o.labels   at the right-hand end: { band, text }, inside the band where it fits
 * o.you      { income, point, label } -- the return's own income, marked
 * o.dot(p)   where the crosshair's dot sits on the stack
 * o.tip(p)   the tooltip's lines at p
 */
function stackChart(o) {
  const W = 720, H = o.height || 300, L = o.left || 40, R = 14, T = 30, B = 30;
  const pts = o.pts, top = pts[pts.length - 1].income, last = pts[pts.length - 1];
  const yMax = o.ticks[o.ticks.length - 1];
  const x = (v) => L + v / top * (W - L - R);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  // tops[k](p) is how high band k reaches at p, everything under it included.
  const tops = o.bands.map((_, k) => (p) => o.bands.slice(0, k + 1).reduce((s, b) => s + b.h(p), 0));
  const stackTop = tops[tops.length - 1];
  const line = (f) => pts.map((p) => `${x(p.income).toFixed(1)},${y(f(p)).toFixed(1)}`);
  const out = [];

  // Where the stack leaves space empty the grid shows there; over the
  // bands it is drawn in the surface colour.
  for (const v of o.ticks.slice(1)) out.push(svgEl('line', { class: 'grid', x1: L, x2: W - R, y1: y(v), y2: y(v) }));
  o.bands.forEach((b, k) => {
    const under = k ? line(tops[k - 1]).reverse() : [`${x(top)},${y(0)}`, `${x(0)},${y(0)}`];
    out.push(svgEl('path', { class: `band ${b.cls}`, d: `M${line(tops[k]).join('L')}L${under.join('L')}Z` }));
  });
  // A line in the surface colour parts neighbouring bands; no outlines.
  o.bands.slice(0, -1).forEach((b, k) => out.push(svgEl('polyline', {
    class: b.gap === 1 ? 'gap thin' : 'gap', points: line(tops[k]).join(' ') })));
  if (o.edge) out.push(svgEl('polyline', { class: 'edge', points: line(stackTop).join(' ') }));

  const gridYs = o.ticks.slice(1, -1).map(y);
  for (const g of gridYs) out.push(svgEl('line', { class: 'grid-over', x1: L, x2: W - R, y1: g, y2: g }));
  for (const v of o.ticks) {
    out.push(svgEl('text', { class: 'tick', x: L - 6, y: y(v) + 4, 'text-anchor': 'end' }, o.tickLabel(v)));
  }
  out.push(svgEl('line', { class: 'axis', x1: L, x2: W - R, y1: y(0), y2: y(0) }));
  for (let v = 0; v <= top; v += 2_500_000) {
    out.push(svgEl('text', { class: 'tick', x: x(v), y: H - 10,
                             'text-anchor': v === 0 ? 'start' : v === top ? 'end' : 'middle' },
                   v === 0 ? '₹0' : `₹${shortInr(v)}`));
  }
  for (const m of (o.marks || []).filter((m) => m.at > 0 && m.at < top)) {
    out.push(svgEl('line', { class: 'threshold', x1: x(m.at), x2: x(m.at), y1: T - 12, y2: y(0) }),
             svgEl('text', { class: 'cap', x: x(m.at) + 4, y: T - 16 }, m.label));
  }

  // Direct labels at the right-hand end, inside their band where they fit,
  // and as near its middle as keeps them clear of the gridlines.
  const clearOf = (lo, hi) => {
    const mid = (lo + hi) / 2;
    for (let d = 0; d <= (hi - lo) / 2; d += 1) {
      for (const c of [mid - d, mid + d]) {
        if (c - 9 >= lo && c + 9 <= hi && gridYs.every((g) => Math.abs(g - c) >= 10)) return c;
      }
    }
    return null;
  };
  for (const lab of o.labels || []) {
    const k = o.bands.findIndex((b) => b.cls === lab.band);
    // A band can slope, so it has to hold the words at both ends of them.
    const span = (p) => [y(tops[k](p)), y(k ? tops[k - 1](p) : 0)];
    const leftAt = (W - R - 8 - (lab.text.length * 7 + 4) - L) / (W - L - R) * top;
    const leftP = pts.reduce((best, p) => (Math.abs(p.income - leftAt) < Math.abs(best.income - leftAt) ? p : best));
    const [lo1, hi1] = span(last), [lo2, hi2] = span(leftP);
    const lo = Math.max(lo1, lo2), hi = Math.min(hi1, hi2);
    const at = hi - lo >= 22 ? clearOf(lo, hi) : null;
    if (at !== null) {
      out.push(svgEl('text', { class: `in in-${lab.band}`, x: W - R - 8, y: at + 4, 'text-anchor': 'end' }, lab.text));
    }
  }

  // The return itself, when its income is on the chart.
  if (o.you) {
    const { income, point, label } = o.you;
    const ux = x(income), right = ux > (L + W - R) / 2;
    out.push(svgEl('line', { class: 'you', x1: ux, x2: ux, y1: y(stackTop(point)), y2: y(0) }),
             svgEl('circle', { class: 'you-dot', cx: ux, cy: y(o.dot(point)), r: 4.5 }));
    if (label) {
      // Above the stack where there is room, else just inside its top.
      const over = y(stackTop(point)) - 10 > T + 4;
      out.push(svgEl('text', { class: 'you-label' + (over ? ' on-surf' : ''), x: right ? ux - 6 : ux + 6,
                               y: over ? y(stackTop(point)) - 10 : y(stackTop(point)) + 16,
                               'text-anchor': right ? 'end' : 'start' }, label));
    }
  }

  // The crosshair: snaps to the nearest point, on hover or with the keys.
  const cross = svgEl('g', { class: 'cross', visibility: 'hidden' },
    svgEl('line', { class: 'cross-line', y1: T, y2: y(0) }),
    svgEl('circle', { class: 'cross-dot', r: 4.5 }));
  out.push(cross);
  let cursor = o.you ? pts.findIndex((p) => p.income >= o.you.income) : Math.round(pts.length / 3);
  const show = (i, cx, cy) => {
    cursor = Math.max(0, Math.min(pts.length - 1, i));
    const p = pts[cursor];
    cross.setAttribute('visibility', 'visible');
    cross.firstChild.setAttribute('x1', x(p.income));
    cross.firstChild.setAttribute('x2', x(p.income));
    cross.lastChild.setAttribute('cx', x(p.income));
    cross.lastChild.setAttribute('cy', y(o.dot(p)));
    showTip(o.tip(p), cx, cy);
  };
  const hit = svgEl('rect', { class: 'hit', x: L, y: T, width: W - L - R, height: y(0) - T, tabindex: '0',
    role: 'img', 'aria-label': `${o.label}, from ₹0 to ₹${shortInr(top)} of taxable income. `
      + 'Use the left and right arrow keys to read the figures at each income.' });
  const svg = svgEl('svg', { class: 'taxshare', viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': o.label },
                    out, hit);
  const nearest = (clientX) => {
    const box = svg.getBoundingClientRect();
    const income = ((clientX - box.left) / box.width * W - L) / (W - L - R) * top;
    let best = 0;
    pts.forEach((p, i) => { if (Math.abs(p.income - income) < Math.abs(pts[best].income - income)) best = i; });
    return best;
  };
  const showAtCross = () => {
    const box = svg.getBoundingClientRect(), scale = box.width / W;
    show(cursor, box.left + x(pts[cursor].income) * scale, box.top + y(o.dot(pts[cursor])) * scale);
  };
  const hide = () => { cross.setAttribute('visibility', 'hidden'); hideTip(); };
  hit.addEventListener('pointermove', (e) => show(nearest(e.clientX), e.clientX, e.clientY));
  hit.addEventListener('pointerleave', hide);
  hit.addEventListener('focus', showAtCross);
  hit.addEventListener('blur', hide);
  hit.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 10 : 1;
    const to = { ArrowRight: cursor + step, ArrowLeft: cursor - step, Home: 0, End: pts.length - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    cursor = Math.max(0, Math.min(pts.length - 1, to));
    showAtCross();
  });
  return svg;
}

/** The tooltip at one income: every part, valued in rupees and as a share
 *  of `of(p)` (the income, or the tax), named after the value. */
function taxTip(p, of, ofWhat) {
  const share = (v) => (of(p) ? ` · ${pct(v / of(p))}` : '');
  const row = (cls, value, label) => el('div', { class: 'tip-row' },
    el('i', { class: `tip-key ${cls}` }), el('b', {}, `${inr(value)}${share(value)}`), el('span', {}, label));
  return [
    el('b', {}, `${inr(p.income)} taxable income`),
    ofWhat === 'income' ? row('kept', p.kept, 'take-home') : null,
    row('tax', p.tax, 'income tax'),
    p.sur ? row('sur', p.sur, 'surcharge') : null,
    row('cess', p.cess, 'cess'),
    el('span', { class: 'tip-sub' }, `${inr(p.total)} of tax in all`
      + (p.income ? `, ${pct(p.total / p.income)} of the income` : ''))];
}

const taxMarks = (curve) => [
  { at: curve.rebate_ceiling, label: `Rebate to ₹${shortInr(curve.rebate_ceiling)}` },
  ...curve.surcharge_bands.map((s) => ({ at: s.from, label: `+${pct(s.rate, 0)} surcharge` }))];

/** How income divides between the tax and take-home, from nothing up to the
 *  top of the curve.
 *
 * Income tax at the bottom, where it reads from the baseline, then surcharge
 * and cess, then take-home above: the tax bands carry the colour and
 * take-home is the quiet remainder. `mode` picks the one y-axis: 'share' of
 * each income (the stack always reaches 100%), or 'amount' in rupees (the
 * stack reaches the income itself, so its top edge is the diagonal). The
 * rebate limit and each surcharge threshold are marked, and `you` (the
 * return's own total income) when it is on the chart.
 */
function taxShareChart(curve, you, mode = 'share') {
  const amount = mode === 'amount';
  const pts = taxPoints(curve);
  const top = pts[pts.length - 1].income, last = pts[pts.length - 1];
  const of = (p, v) => (amount ? v : p.income ? v / p.income : 0);
  const say = (v, p) => (amount ? `₹${shortInr(v)}` : pct(v / p.income));
  const mine = you ? taxPoints({ income: [you.income], tax: [you.tax], surcharge: [you.surcharge], cess: [you.cess] })[0] : null;
  return stackChart({
    pts,
    left: amount ? 56 : 40,
    // Surcharge and cess are thin beside the whole income, so the lines
    // between the tax bands are 1px; the line under take-home is the full 2px.
    bands: [{ cls: 'tax', h: (p) => of(p, p.tax), gap: 1 },
            { cls: 'sur', h: (p) => of(p, p.sur), gap: 1 },
            { cls: 'cess', h: (p) => of(p, p.cess), gap: 2 },
            { cls: 'kept', h: (p) => (amount ? p.kept : p.income ? p.kept / p.income : 1) }],
    ticks: amount ? Array.from({ length: Math.floor(top / 2_500_000) + 1 }, (_, i) => i * 2_500_000)
                  : [0, 0.25, 0.5, 0.75, 1],
    tickLabel: (v) => (amount ? (v ? `₹${shortInr(v)}` : '₹0') : pct(v, 0)),
    marks: taxMarks(curve),
    edge: amount,
    labels: [{ band: 'kept', text: `Take-home ${say(last.kept, last)}` },
             { band: 'tax', text: `Income tax ${say(last.tax, last)}` }],
    you: mine ? { income: mine.income, point: mine, label: `Your income ₹${shortInr(mine.income)}` } : null,
    dot: (p) => of(p, p.total),
    tip: (p) => taxTip(p, (q) => q.income, 'income'),
    label: `Take-home, income tax, surcharge and cess ${amount ? 'in rupees' : 'as shares of'} taxable income`,
  });
}

/** What the tax itself is made of, at each income: income tax, surcharge and
 *  cess, as shares of the tax (so the surcharge and cess are big enough to
 *  see) or in rupees. Nothing is stacked where there is no tax. */
function taxMixChart(curve, you, mode = 'share') {
  const amount = mode === 'amount';
  const pts = taxPoints(curve);
  const last = pts[pts.length - 1];
  const of = (p, v) => (amount ? v : p.total ? v / p.total : 0);
  const say = (v, p) => (amount ? `₹${shortInr(v)}` : pct(v / p.total));
  const ticks = amount ? rupeeTicks(Math.max(...pts.map((p) => p.total))) : [0, 0.25, 0.5, 0.75, 1];
  const mine = you ? taxPoints({ income: [you.income], tax: [you.tax], surcharge: [you.surcharge], cess: [you.cess] })[0] : null;
  return stackChart({
    pts,
    height: 250,
    left: amount ? 56 : 40,
    bands: [{ cls: 'tax', h: (p) => of(p, p.tax) },
            { cls: 'sur', h: (p) => of(p, p.sur) },
            { cls: 'cess', h: (p) => of(p, p.cess) }],
    ticks,
    tickLabel: (v) => (amount ? (v ? `₹${shortInr(v)}` : '₹0') : pct(v, 0)),
    marks: taxMarks(curve),
    labels: [{ band: 'tax', text: `Income tax ${say(last.tax, last)}` },
             { band: 'sur', text: `Surcharge ${say(last.sur, last)}` }],
    you: mine && mine.total ? { income: mine.income, point: mine } : null,
    dot: (p) => of(p, p.tax),
    tip: (p) => taxTip(p, (q) => q.total, 'tax'),
    label: `Income tax, surcharge and cess ${amount ? 'in rupees' : 'as shares of the tax'}`,
  });
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
