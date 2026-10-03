/* Flow: the places that are not a schedule.
 *
 * Summary, Documents, Review, Reconcile and Hand-off. They are places, not
 * steps: nothing here is numbered, nothing waits on anything else, and each
 * says what it needs as a status rather than as a position in a sequence. A
 * return is not built in a straight line -- a document turns up late, a
 * schedule is read again, a decision moves a figure -- and a page that
 * pretends otherwise gets in the way.
 *
 * Everything on these pages is read from what the schedules already hold.
 * Nothing is computed here that changes a figure.
 */

// What a person has chosen to look at on each page. Kept apart from the data
// so a refresh redraws the same view rather than resetting it.
state.ui = {
  review: { view: 'decide', tab: '', q: '', picked: new Set() },
  documents: { view: 'all', q: '', open: null },
  recon: { check: null },
};

/* ---------------------------------------------------------- small helpers */

/** Rupees with the sign in front of the symbol, where a minus belongs. */
const inr = (n) =>
  (typeof n !== 'number' ? '—' : (n < 0 ? '−₹' : '₹') + rupees(Math.abs(n)));

const plural = (n, one, many) =>
  `${Number(n).toLocaleString('en-IN')} ${n === 1 ? one : (many || one + 's')}`;

const clip = (text, n) => {
  const s = String(text || '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
};

const baseName = (path) => String(path || '').split('/').pop();

const chip = (text, tone = '', title = '') =>
  el('span', { class: 'chip' + (tone ? ' ' + tone : ''), title: title || null }, text);

const sec = (title, ...kids) => el('div', { class: 'sec' }, el('h3', {}, title), ...kids);

/** An identity for a thing that has no id of its own: a question is known by
 *  what it says. Stable across page loads, which is all that is asked of it. */
function hashId(text) {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

/** "today, 10:49" or "30 Sep, 14:45": when something was read or computed. */
function fmtWhen(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const now = new Date();
  const time = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
  if (d.toDateString() === now.toDateString()) return `today, ${time}`;
  const date = d.toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short',
    year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  });
  return `${date}, ${time}`;
}

const fmtDay = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso || '')
    : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
};

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // An older browser, or a page not in focus: the long way round.
    const area = el('textarea', { style: 'position:fixed;opacity:0' }, text);
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  if (button) {
    button.classList.add('done');
    setTimeout(() => button.classList.remove('done'), 1400);
  }
}

function download(name, text, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = el('a', { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

const csvCell = (v) => {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/* ------------------------------------------------- what needs a decision */

const KIND = {
  difference: { label: 'Unexplained difference', tone: 'warn', order: 0 },
  check: { label: 'Check failed', tone: 'err', order: 1 },
  rate: { label: 'Rate needed', tone: 'warn', order: 2 },
  unread: { label: 'Not read', tone: 'warn', order: 3 },
  question: { label: 'Question', tone: 'info', order: 4 },
  set_aside: { label: 'Set aside', tone: '', order: 5 },
};

// The answers that make sense for each kind of item. The words are the
// server's, so the record and the page cannot drift apart.
const CHOICES_FOR = {
  question: ['no_change', 'will_correct', 'not_relevant'],
  set_aside: ['left_out', 'elsewhere', 'will_correct'],
  difference: ['accepted', 'will_correct', 'department'],
  check: ['no_change', 'will_correct'],
  rate: ['no_change', 'will_correct'],
  unread: ['not_relevant', 'will_correct'],
};

/** Everything a person is asked to look at, from every schedule, as one list.
 *
 * Two kinds of thing are kept apart. A question, an unexplained difference, a
 * missing rate or an unread document is waiting on a person, and counts as an
 * open decision. Something the reading found and deliberately did not place --
 * a TDS figure on a salary certificate, a credit of unknown nature -- is a
 * disclosure: it is listed, sized and can be confirmed, but it is not counted
 * as open, because most of it is exactly where it should be.
 */
function reviewItems() {
  if (state.cache.items) return state.cache.items;
  const settled = state.decisions?.current || {};
  const items = [];
  const seen = new Map();
  const order = new Map(state.tabs.map((t, i) => [t.id, i]));

  const add = (item) => {
    const key = `${item.tab}|${item.kind}|${item.text}`;
    const n = seen.get(key) || 0;
    seen.set(key, n + 1);
    const id = hashId(n ? `${key}#${n}` : key);
    items.push({ ...item, id, settled: settled[id] || null, counts: item.kind !== 'set_aside' });
  };

  for (const tab of state.tabs) {
    const d = tab.document;
    if (d && tab.id !== 'summary') {
      for (const q of d.questions || []) {
        if (typeof q === 'string' && q.trim()) add({ tab: tab.id, kind: 'question', text: q, from: 'the reading' });
      }
      for (const u of d.unmapped || []) {
        add({
          tab: tab.id, kind: 'set_aside', text: u.text || u.why || 'Found but not placed',
          why: u.why || '', source: u.source || '',
          amount: typeof u.amount?.amount === 'number' ? u.amount.amount : null,
          cite: u.amount?.cite || null, basis: u.amount?.basis || null,
        });
      }
    }
    const r = tab.reconciliation;
    if (r) {
      for (const q of r.questions || []) {
        if (typeof q === 'string' && q.trim()) add({ tab: tab.id, kind: 'question', text: q, from: 'the reconciliation' });
      }
      for (const g of (r.groups || []).filter((x) => x.status === 'unexplained')) {
        add({
          tab: tab.id, kind: 'difference', amount: Math.abs(g.unaccounted || g.difference || 0),
          text: `${g.label}: your documents give ${inr(g.ours)} and the department’s record `
              + `${inr(g.reported)}. ${inr(Math.abs(g.unaccounted || 0))} of the difference is not accounted for.`,
          measure: g.measure,
        });
      }
      for (const ln of (r.lines || []).filter((x) => x.status === 'unexplained')) {
        add({
          tab: tab.id, kind: 'difference', amount: Math.abs(ln.unaccounted || ln.difference || 0),
          text: `${ln.category}: your documents give ${inr(ln.ours)} and the department’s record `
              + `${inr((ln.reported || {}).amount)}. ${inr(Math.abs(ln.unaccounted || ln.difference || 0))} `
              + 'of the difference is not accounted for.',
          cite: (ln.reported || {}).cite || null, source: ln.source || '',
        });
      }
    }
  }

  const summary = state.tabs.find((t) => t.id === 'summary')?.document;
  for (const c of (summary?.checks || []).filter((x) => !x.ok)) {
    add({ tab: 'summary', kind: 'check', text: `${c.check}. ${c.detail}` });
  }
  const regime = computedRegime();
  const rates = [
    ['capital_gains', regime?.capital_gains?.rates_needed],
    ['foreign_special', regime?.foreign_assets?.rates_needed],
  ];
  for (const [tabId, needed] of rates) {
    if (!needed?.length) continue;
    add({
      tab: tabId, kind: 'rate',
      text: `${plural(needed.length, 'exchange rate is', 'exchange rates are')} still needed: `
          + needed.slice(0, 6).map((x) => `${x.currency} on ${x.date}`).join(', ')
          + (needed.length > 6 ? ' and others' : '')
          + '. The amounts on those dates are left out of every figure until the rate is in.',
    });
  }
  for (const u of state.unassigned || []) {
    add({
      tab: 'documents', kind: 'unread', source: u.path,
      text: `${baseName(u.path)} is in the documents folder, but no schedule reads it.`
          + (u.is_archive ? ' It is an archive nothing can read inside.' : ''),
    });
  }

  items.sort((a, b) =>
    (KIND[a.kind].order - KIND[b.kind].order)
    || (a.kind === 'question' ? 0 : (b.amount || 0) - (a.amount || 0))
    || ((order.get(a.tab) ?? 99) - (order.get(b.tab) ?? 99)));
  state.cache.items = items;
  return items;
}

const openDecisions = (tabId) =>
  reviewItems().filter((i) => i.counts && !i.settled && (!tabId || i.tab === tabId));

const setAside = (tabId) =>
  reviewItems().filter((i) => !i.counts && !i.settled && (!tabId || i.tab === tabId));

/** Decisions made about something a later reading no longer raises. */
function orphanedDecisions() {
  const live = new Set(reviewItems().map((i) => i.id));
  return Object.values(state.decisions?.current || {}).filter((e) => !live.has(e.id));
}

/** One more rupee of ordinary income costs this much: slab rate, surcharge
 *  and cess. Used only to size an open item, never to compute anything. */
const marginalRate = () => computedRegime()?.marginal_rate || 0;

function atStake(item) {
  if (!item.amount || !marginalRate() || item.tab === 'filed_return') return null;
  return Math.round(item.amount * marginalRate());
}

async function settleItems(items, choice, reason) {
  for (const item of items) {
    const res = await api('/api/decisions', {
      method: 'POST',
      body: JSON.stringify({
        ay: state.ay, choice, reason,
        item: { id: item.id, tab: item.tab, kind: item.kind, text: item.text, amount: item.amount ?? null },
      }),
    });
    state.decisions = (await res.json()).decisions;
  }
  state.cache = {};
}

async function reopenItem(id) {
  const res = await api('/api/decisions', {
    method: 'POST', body: JSON.stringify({ ay: state.ay, action: 'reopen', id }),
  });
  state.decisions = (await res.json()).decisions;
  state.cache = {};
}

/** The form that settles one item, or several at once.
 *
 * A reason is required. Without it a decision is just a tick, and a tick
 * explains nothing to whoever opens this return in three years. */
function decideForm(items, after) {
  const kind = items[0].kind;
  const options = (CHOICES_FOR[kind] || CHOICES_FOR.question)
    .filter((key) => state.choices?.[key]);
  const name = `choice-${items[0].id}`;
  const reason = el('textarea', {
    rows: '3', 'aria-label': 'Reason',
    placeholder: 'Why this is the right call. Write it for someone reading it in three years.',
  });
  const problem = el('span', { class: 'err-text', role: 'alert' });
  const radios = options.map((key, i) => el('label', { class: 'choice' },
    el('input', { type: 'radio', name, value: key, checked: i === 0 }),
    el('span', {}, state.choices[key])));

  const apply = el('button', { class: 'primary', type: 'button', onclick: async () => {
    const chosen = radios.map((r) => r.querySelector('input')).find((r) => r.checked)?.value;
    const why = reason.value.trim();
    if (!why) {
      problem.textContent = 'A decision needs its reason.';
      reason.focus();
      return;
    }
    apply.disabled = true;
    try {
      await settleItems(items, chosen, why);
      toast(items.length === 1 ? 'Settled, and kept with its reason.'
                               : `${plural(items.length, 'item')} settled together.`);
      after?.();
    } catch (err) {
      problem.textContent = err.message;
      apply.disabled = false;
    }
  } }, items.length === 1 ? 'Settle' : `Settle ${items.length} together`);

  return el('div', { class: 'decide' }, ...radios, reason,
    el('div', { class: 'acts-row' }, apply, problem));
}

function settledBlock(entry, after) {
  return el('div', { class: 'settled' },
    el('b', {}, entry.choice_label || 'Settled'),
    el('p', {}, entry.reason),
    el('small', {}, `Settled ${fmtWhen(entry.at)}. `,
      el('button', { class: 'linkish', style: 'color:inherit;text-decoration:underline',
                     onclick: async () => {
                       try { await reopenItem(entry.id); toast('Reopened.'); after?.(); }
                       catch (err) { toast(err.message, 'err'); }
                     } }, 'Reopen')));
}

/** Everything known about one item, and the decision on it. */
function itemDetail(item, after) {
  const meta = KIND[item.kind];
  const stake = atStake(item);
  const body = [];

  // The heading carries the first sentence; the rest follows it here, so a
  // short item is not said twice.
  const title = itemTitle(item.text);
  const rest = item.text.slice(title.replace(/\u2026$/, '').length).trim();
  if (rest || item.why || item.from) {
    body.push(sec(item.kind === 'set_aside' ? 'What was found' : 'The rest of it',
      rest ? el('p', { style: 'color:var(--ink)' }, rest) : null,
      item.why ? el('p', {}, item.why) : null,
      item.from ? el('p', { class: 'muted' }, `Raised by ${item.from} of ${tabName(item.tab)}.`) : null));
  }

  if (typeof item.amount === 'number' && item.amount) {
    const isDifference = item.kind === 'difference';
    body.push(sec(isDifference ? 'What it could be worth' : 'The amount it names',
      el('dl', { class: 'dl' },
        el('dt', {}, isDifference ? 'Not accounted for' : 'Amount'),
        el('dd', {}, inr(item.amount)),
        stake ? el('dt', {}, isDifference ? 'Tax, if all of it were income at normal rates'
                                          : 'Tax on it, only if it is income not yet on any line') : null,
        stake ? el('dd', {}, `about ${inr(stake)}`) : null),
      stake ? el('p', { class: 'muted', style: 'margin-top:8px;font-size:12.5px' },
        (isDifference ? '' : 'Most of what a reading sets aside is already in the return on '
          + 'another schedule, where this figure does not apply. ')
        + `At ${(marginalRate() * 100).toFixed(2)}%: the slab rate this return has reached, with `
        + 'surcharge and cess. It is a ceiling for sizing the item, not a computation.') : null));
  }

  if (item.source || item.cite) {
    const path = item.source || String(item.cite || '').split('#')[0];
    body.push(sec('Where it is from',
      el('p', { class: 'mono', style: 'font-size:12px' }, item.cite || baseName(item.source)),
      item.cite && item.amount ? excerptBlock(item.cite, item.amount, item.source) : null,
      el('div', { style: 'margin-top:8px' },
        el('button', { class: 'ghost small', onclick: () => openDocument(path) },
           icon('open'), 'Open the document'))));
  }

  body.push(sec('Your decision',
    item.settled ? settledBlock(item.settled, after) : decideForm([item], after)));

  const known = state.tabs.some((t) => t.id === item.tab);
  return [
    el('div', { class: 'detail-head' },
      el('div', { class: 'chips' }, chip(meta.label, meta.tone),
         known ? el('a', { class: 'chip line', href: `#${item.tab}` }, tabName(item.tab)) : null),
      el('h2', {}, title)),
    el('div', { class: 'detail-body' }, ...body),
  ];
}

/** The first sentence of an item, for its heading. */
function itemTitle(text) {
  const s = String(text || '');
  const stop = s.search(/[.?!](\s|$)/);
  if (stop > 20 && stop < 200) return s.slice(0, stop + 1);
  return s.length > 200 ? s.slice(0, 199) + '\u2026' : s;
}

/* ------------------------------------------------------------------ review */

function pageReview() {
  const ui = state.ui.review;
  const all = reviewItems();
  const orphans = orphanedDecisions();
  const views = {
    decide: all.filter((i) => i.counts && !i.settled),
    aside: all.filter((i) => !i.counts && !i.settled),
    settled: all.filter((i) => i.settled),
  };
  if (!views[ui.view]) ui.view = 'decide';

  const inTab = (i) => !ui.tab || i.tab === ui.tab;
  const q = ui.q.trim().toLowerCase();
  const matches = (i) => !q || `${i.text} ${i.why || ''} ${i.source || ''}`.toLowerCase().includes(q);
  const list = views[ui.view].filter(inTab).filter(matches);

  // A link can name the item to open: .../#review/<id>
  let current = all.find((i) => i.id === state.sub);
  if (current && !list.includes(current)) {
    // Asked for by name but outside the current filter: show it anyway.
    ui.view = current.settled ? 'settled' : current.counts ? 'decide' : 'aside';
    ui.tab = '';
    ui.q = '';
    return pageReview();
  }
  if (!current) current = list[0] || null;

  const redraw = () => { renderRail(); renderPanel(); };
  const after = () => {
    // Move on to the next one still open, so settling a run of items is one
    // decision after another rather than a hunt back through the list.
    const at = list.indexOf(current);
    const next = list.slice(at + 1).concat(list.slice(0, at)).find((i) => !i.settled);
    state.sub = ui.view === 'settled' ? current.id : next?.id || null;
    redraw();
  };

  const tabsWithItems = [...new Set(views[ui.view].map((i) => i.tab))];
  const seg = (key, label) => el('button', {
    type: 'button', 'aria-pressed': String(ui.view === key),
    onclick: () => { ui.view = key; ui.picked.clear(); state.sub = null; renderPanel(); },
  }, label, el('span', { class: 'n' }, String(views[key].length)));

  const search = el('input', { type: 'search', placeholder: 'Filter by words', value: ui.q,
                               'aria-label': 'Filter the list' });
  search.addEventListener('input', () => {
    ui.q = search.value;
    state.sub = null;
    renderPanel();
    const again = $('#panel input[type="search"]');
    again?.focus();
    again?.setSelectionRange(again.value.length, again.value.length);
  });
  const scope = el('select', { 'aria-label': 'Schedule', onchange: (e) => {
    ui.tab = e.target.value; state.sub = null; renderPanel();
  } }, el('option', { value: '' }, 'Every schedule'),
     ...tabsWithItems.map((id) => el('option', { value: id }, tabName(id))));
  scope.value = tabsWithItems.includes(ui.tab) ? ui.tab : '';

  const picked = list.filter((i) => ui.picked.has(i.id));
  const rows = list.map((item) => {
    const meta = KIND[item.kind];
    const stake = atStake(item);
    const pick = ui.view === 'aside'
      ? el('input', { type: 'checkbox', checked: ui.picked.has(item.id),
                      'aria-label': 'Select to settle together',
                      onclick: (e) => {
                        e.stopPropagation();
                        if (e.target.checked) ui.picked.add(item.id); else ui.picked.delete(item.id);
                        renderPanel();
                      } })
      : null;
    return el('div', {
      class: 'row' + (pick ? ' row-check' : '') + (current === item && !picked.length ? ' selected' : '')
           + (item.settled ? ' done' : ''),
      role: 'button', tabindex: '0',
      onclick: () => { ui.picked.clear(); select('review', item.id); },
      onkeydown: (e) => { if (e.key === 'Enter') { ui.picked.clear(); select('review', item.id); } },
    },
      pick,
      el('div', { class: 'row-main' },
        el('div', { class: 'row-t' }, item.text),
        el('div', { class: 'row-sub' }, chip(meta.label, meta.tone),
           el('span', {}, state.tabs.some((t) => t.id === item.tab) ? tabName(item.tab) : 'Documents'),
           item.settled ? el('span', {}, `settled ${fmtWhen(item.settled.at)}`) : null)),
      typeof item.amount === 'number' && item.amount
        ? el('div', { class: 'row-end' }, inr(item.amount),
             stake && item.kind === 'difference' ? el('small', {}, `up to ${inr(stake)} of tax`) : null)
        : el('div', { class: 'row-end' }));
  });

  let detail;
  if (picked.length) {
    const total = picked.reduce((a, i) => a + (i.amount || 0), 0);
    detail = [
      el('div', { class: 'detail-head' },
        el('div', { class: 'chips' }, chip(`${picked.length} selected`, 'info')),
        el('h2', {}, 'Settle these together')),
      el('div', { class: 'detail-body' },
        sec('What is selected',
          el('p', {}, `${plural(picked.length, 'item')} set aside`
             + (total ? `, ${inr(total)} between them.` : '.')),
          el('ul', { class: 'plain' }, picked.slice(0, 6).map((i) =>
            el('li', { style: 'font-size:12.5px' }, clip(i.text, 110)))),
          picked.length > 6 ? el('p', { class: 'muted' }, `and ${picked.length - 6} more`) : null),
        sec('One decision for all of them',
          decideForm(picked, () => { ui.picked.clear(); state.sub = null; redraw(); }))),
    ];
  } else if (current) {
    detail = itemDetail(current, after);
  } else {
    detail = [el('div', { class: 'empty-state' },
      el('h3', {}, 'Nothing selected'),
      el('p', {}, 'Choose an item on the left to see what it is about and to settle it.'))];
  }

  const emptyText = {
    decide: ['Nothing is waiting on you', 'Every question, difference and missing rate has been settled, or none was raised.'],
    aside: ['Nothing is set aside', 'Everything the readings found has been placed on a line.'],
    settled: ['Nothing settled yet', 'Decisions you make are kept here with their reasons.'],
  }[ui.view];

  return [
    el('div', { class: 'page-head' },
      el('div', {},
        el('div', { class: 'page-title' }, el('h1', {}, 'Review')),
        el('p', { class: 'page-sub' },
          'What only a person can settle: questions the documents do not answer, differences '
          + 'nothing accounts for, and what each reading found and left out. Every decision is '
          + 'kept with its reason.'))),
    el('div', { class: 'toolbar' },
      el('div', { class: 'seg', role: 'group', 'aria-label': 'Which items' },
        seg('decide', 'To decide'), seg('aside', 'Set aside'), seg('settled', 'Settled')),
      scope, search,
      el('span', { class: 'grow' }),
      ui.view === 'aside' && list.length
        ? el('button', { class: 'ghost small', onclick: () => {
            if (picked.length === list.length) ui.picked.clear();
            else list.forEach((i) => ui.picked.add(i.id));
            renderPanel();
          } }, picked.length === list.length ? 'Clear the selection' : `Select all ${list.length}`)
        : null),
    el('div', { class: 'split' },
      el('section', { class: 'card' },
        rows.length
          ? el('div', { class: 'rows' }, ...rows)
          : el('div', { class: 'empty-state' }, el('h3', {}, emptyText[0]), el('p', {}, emptyText[1])),
        ui.view === 'settled' && orphans.length
          ? el('div', { class: 'card-foot' },
              `${plural(orphans.length, 'earlier decision is', 'earlier decisions are')} about `
              + 'something a later reading no longer raises. They stay in the record on the Hand-off page.')
          : null),
      el('section', { class: 'card detail' }, ...detail)),
  ];
}

/** The decisions of one schedule, on its own page. */
function scheduleDecisions(tab) {
  const items = reviewItems().filter((i) => i.tab === tab.id);
  const open = items.filter((i) => i.counts && !i.settled);
  const aside = items.filter((i) => !i.counts && !i.settled);
  const done = items.filter((i) => i.settled);
  const redraw = () => { renderRail(); renderPanel(); };

  const block = (title, list, note, cls = '') => {
    if (!list.length) return null;
    const rows = [];
    list.forEach((item) => {
      const row = el('tr', {},
        el('td', {}, item.text,
           item.why ? el('span', { class: 'why' }, item.why) : null,
           item.source ? el('span', { class: 'src' }, baseName(item.source)) : null),
        el('td', { class: 'num' }, typeof item.amount === 'number' && item.amount ? rupees(item.amount) : ''),
        el('td', { class: 'nowrap' }, item.settled ? chip('Settled', 'ok') : chip(KIND[item.kind].label, KIND[item.kind].tone)));
      const inner = el('tr', {}, el('td', { colspan: '3', style: 'background:var(--surf2)' },
        el('div', { style: 'max-width:640px' },
          item.settled ? settledBlock(item.settled, redraw) : decideForm([item], redraw))));
      const trunk = branch(row, [branch(inner)]);
      rows.push(...trunk.rows);
    });
    return card(`${title} (${list.length})`,
      table(['What it says', { t: 'Amount', num: true }, ''], rows), cls,
      el('span', { class: 'src' }, note));
  };

  const cards = [
    block('To decide', open, 'open a row to settle it, with the reason', 'warn'),
    block('Found and set aside', aside,
          'what the reading found and did not place on a line; confirm or correct each'),
    block('Settled', done, 'kept with the reason; any of them can be reopened'),
  ].filter(Boolean);
  if (cards.length) return cards;
  return [el('section', { class: 'card' }, el('div', { class: 'empty-state' },
    el('h3', {}, 'Nothing to decide on this schedule'),
    el('p', {}, tab.document ? 'The reading raised no question and set nothing aside.'
                             : 'Nothing has been read for this schedule yet.')))];
}

/* --------------------------------------------------------------- documents */

/** Every document of this return, with what it was taken for and whether
 *  each schedule that wants it has actually read it. */
function allDocuments() {
  if (state.cache.docs) return state.cache.docs;
  const byPath = new Map();
  const get = (path) => {
    if (!byPath.has(path)) {
      byPath.set(path, {
        path, key: hashId(path), name: baseName(path),
        folder: path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '',
        bytes: null, feeds: [], kind: '', why: '', confidence: '', duplicateOf: null,
        unsorted: false, isArchive: false,
      });
    }
    return byPath.get(path);
  };

  for (const tab of state.tabs) {
    // A derived schedule is computed from other schedules; it reads no
    // document itself, so no document feeds it and none is waiting on it.
    if (tab.kind === 'derive') continue;
    const d = tab.document;
    const gaps = [...(d?.questions || []), ...(d?.unmapped || []).map((u) => `${u.text || ''} ${u.why || ''}`)]
      .filter((g) => typeof g === 'string');
    for (const f of tab.documents || []) {
      const entry = get(f.path);
      entry.bytes = f.bytes;
      // A reading that had trouble with a document says so in a note. That is
      // something to go and read, not proof the document went unread.
      const noted = gaps.some((g) => g.includes(f.name)
        && /NOT READ|not covered|could not|unable|couldn't/i.test(g));
      entry.feeds.push({ tab: tab.id, read: Boolean(f.read_last_run), noted, via: f.via,
                         everRead: Boolean(d) });
      for (const dup of f.duplicates || []) if (dup !== f.path) get(dup).duplicateOf = f.path;
    }
  }
  for (const m of state.documentMap?.documents || []) {
    const entry = get(m.path);
    entry.kind = m.kind || '';
    entry.why = m.why || '';
    entry.confidence = m.confidence || '';
    entry.opened = Boolean(m.opened);
  }
  for (const u of state.unassigned || []) {
    const entry = get(u.path);
    entry.unsorted = true;
    entry.bytes = u.bytes;
    entry.isArchive = Boolean(u.is_archive);
  }

  const docs = [...byPath.values()];
  for (const d of docs) d.state = documentState(d);
  docs.sort((a, b) => (a.state.rank - b.state.rank) || a.folder.localeCompare(b.folder)
                      || a.name.localeCompare(b.name));
  state.cache.docs = docs;
  return docs;
}

function documentState(d) {
  if (d.unsorted) return { key: 'unsorted', label: 'No schedule reads it', tone: 'warn', rank: 0, attention: true };
  if (d.duplicateOf && !d.feeds.length) return { key: 'duplicate', label: 'Duplicate copy', tone: '', rank: 6 };
  if (!d.feeds.length) return { key: 'aside', label: 'Not used', tone: '', rank: 5 };
  // A schedule that has never been read at all is not this document's
  // fault; only schedules that have been read can have skipped it.
  const wanted = d.feeds.filter((f) => f.everRead);
  const read = d.feeds.filter((f) => f.read).length;
  if (!read && wanted.length) return { key: 'skipped', label: 'Not in the last reading', tone: 'warn', rank: 2, attention: true };
  if (!read) return { key: 'waiting', label: 'Waiting to be read', tone: 'line', rank: 3 };
  if (d.feeds.some((f) => f.read && f.noted)) return { key: 'noted', label: 'Read, with a note', tone: 'warn', rank: 1 };
  if (read < d.feeds.length) return { key: 'partly', label: `Read by ${read} of ${d.feeds.length}`, tone: 'ok', rank: 4 };
  return { key: 'read', label: 'Read', tone: 'ok', rank: 4 };
}

const documentsNeedingAttention = () => allDocuments().filter((d) => d.state.attention);

/** The figures a document supplied: every amount that cites it. */
function figuresFrom(d) {
  const out = [];
  const walk = (node, tabId) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach((n) => walk(n, tabId)); return; }
    if (typeof node.cite === 'string' && (node.amount !== undefined || node.amount_foreign !== undefined)) {
      if (node.cite.includes(d.name)) {
        out.push({ tab: tabId, amount: node.amount, cite: node.cite, basis: node.basis || '',
                   foreign: node.amount === undefined ? foreignAmount(node) : null });
      }
      return;
    }
    Object.values(node).forEach((v) => walk(v, tabId));
  };
  d.feeds.forEach((f) => walk(state.tabs.find((t) => t.id === f.tab)?.document?.data, f.tab));
  return out;
}

function documentDetail(d) {
  const figures = figuresFrom(d);
  const aside = reviewItems().filter((i) => i.kind === 'set_aside' && i.source && baseName(i.source) === d.name);
  const mentions = reviewItems().filter((i) => i.kind === 'question' && i.text.includes(d.name));
  const shown = figures.slice().sort((a, b) => Math.abs(b.amount || 0) - Math.abs(a.amount || 0)).slice(0, 8);

  return [
    el('div', { class: 'detail-head' },
      el('div', { class: 'chips' }, chip(d.state.label, d.state.tone),
         d.confidence && d.confidence !== 'high' ? chip(`${d.confidence} confidence`, 'warn') : null),
      el('h2', {}, d.name),
      el('div', { class: 'src', style: 'margin-top:4px;overflow-wrap:anywhere' },
         [d.folder, d.bytes ? KB(d.bytes) : null].filter(Boolean).join(' · '))),
    el('div', { class: 'detail-body' },
      sec('Recognised as',
        el('p', { style: 'color:var(--ink)' }, d.kind || (d.unsorted
          ? 'Not recognised: it has not been sorted into any schedule.'
          : 'Placed by a folder rule, without being sorted.')),
        d.why ? el('p', {}, d.why) : null,
        d.duplicateOf ? el('p', {}, `The same file, byte for byte, as ${baseName(d.duplicateOf)} in `
          + `${d.duplicateOf.includes('/') ? d.duplicateOf.slice(0, d.duplicateOf.lastIndexOf('/')) : 'the top folder'}. `
          + 'Only one copy is read, so nothing is counted twice.') : null),
      sec('Feeds',
        d.feeds.length
          ? el('ul', { class: 'plain' }, d.feeds.map((f) => el('li', {
              style: 'display:flex;gap:10px;align-items:center;justify-content:space-between',
            },
              el('a', { href: `#${f.tab}/documents` }, tabName(f.tab)),
              f.read && f.noted ? el('a', { class: 'chip warn', href: `#${f.tab}/decisions`,
                                            title: 'The reading left a note that names this document' },
                                     'Read, with a note')
                : f.read ? chip('Read', 'ok')
                : f.everRead ? chip('Not in the last reading', 'warn') : chip('Schedule not read yet', 'line'))))
          : el('p', {}, d.unsorted
              ? 'No schedule. Sort the documents again, or move the file into a folder a schedule reads.'
              : 'No schedule reads this file.')),
      sec(`What was taken (${figures.length})`,
        figures.length
          ? el('table', { class: 'sum' }, el('tbody', {}, shown.map((f) => el('tr', {},
              el('td', {}, f.basis || f.cite, el('span', { class: 'why' }, tabName(f.tab))),
              el('td', { class: 'num' }, f.foreign || rupees(f.amount))))))
          : el('p', {}, d.feeds.some((f) => f.read)
              ? 'It was read, but no figure cites it. Its rows may be in a ledger that cites the sheet or page instead.'
              : 'Nothing yet.'),
        figures.length > shown.length
          ? el('p', { class: 'muted', style: 'margin-top:8px' },
               `The ${shown.length} largest of ${figures.length} are shown.`) : null),
      aside.length ? sec(`Set aside (${aside.length})`,
        el('ul', { class: 'plain' }, aside.slice(0, 6).map((i) => el('li', {},
          el('a', { href: `#review/${i.id}` }, clip(i.text, 120)),
          typeof i.amount === 'number' && i.amount ? el('span', { class: 'why' }, inr(i.amount)) : null))),
        aside.length > 6 ? el('p', { class: 'muted', style: 'margin-top:8px' }, `and ${aside.length - 6} more in Review`) : null) : null,
      mentions.length ? sec(`Questions that name it (${mentions.length})`,
        el('ul', { class: 'plain' }, mentions.slice(0, 4).map((i) => el('li', {},
          el('a', { href: `#review/${i.id}` }, clip(i.text, 140)))))) : null,
      el('div', { class: 'sec' },
        el('button', { class: 'ghost small', onclick: () => openDocument(d.path) },
           icon('open'), 'Open the document'))),
  ];
}

/* ----------------------------------------------------------- get documents */

/** {fy} and friends, from the return's own year. */
function fillYear(text) {
  const fy = state.fy || '';
  const start = Number(fy.slice(0, 4)) || 0;
  const tokens = start ? {
    fy, ay: `${start + 1}-${String(start + 2).slice(-2)}`,
    fy_start: `1 April ${start}`, fy_end: `31 March ${start + 1}`,
    fy_end_year: String(start + 1), cy: String(start),
  } : {};
  return String(text || '').replace(/\{(\w+)\}/g, (all, key) => tokens[key] ?? all);
}

/** Documents in this return's folder that look like a guide entry, by what
 *  sorting recognised them as. A hint for the reader, never used to compute. */
function seenIn(patterns, within = null) {
  const compile = (list) => (list || []).map((p) => { try { return new RegExp(p, 'i'); } catch { return null; } }).filter(Boolean);
  const res = compile(patterns);
  const scope = compile(within);
  if (!res.length) return [];
  return (state.documentMap?.documents || []).filter((d) => res.some((re) => re.test(d.kind || ''))
    && (!scope.length || scope.some((re) => re.test(d.kind || ''))));
}

async function openDocumentsFolder() {
  try {
    await api('/api/open-folder', { method: 'POST', body: JSON.stringify({ ay: state.ay }) });
  } catch (err) {
    toast(`Could not open the folder: ${err.message}`, 'err');
  }
}

/** The tabs at the top of the Documents page. */
function documentTabs(active, count) {
  const tab = (id, label, href, n) => el('a', { class: 'tab', role: 'tab', href, 'aria-selected': String(id === active) },
    label, n ? el('span', { class: 'tab-count' }, String(n)) : null);
  return el('div', { class: 'tabs', role: 'tablist', style: 'margin-bottom:16px' },
    tab('folder', 'In your folder', '#documents', count),
    tab('get', 'Get documents', '#documents/get'));
}

/** Where each usual document comes from and how to download it. Flow opens
 *  the site and shows the steps; the person logs in and downloads. */
function getDocumentsView() {
  const guide = state.sources || {};
  const p = state.activeProfile || {};
  const docs = allDocuments();

  // A bank's documents are the same for every bank, so they count only when
  // they are that bank's: "statement" alone would match every bank at once.
  const docBlock = (d, src) => {
    const seen = seenIn(d.match, src.bank ? src.match : null);
    return el('div', { class: 'gd-doc' },
      el('div', { class: 'gd-doc-h' },
        el('b', {}, fillYear(d.name)),
        seen.length ? chip(seen.length > 1 ? `${seen.length} in your folder` : 'In your folder', 'ok') : null),
      (d.for || []).length ? el('div', { class: 'gd-for' }, 'Used for ',
        (d.for || []).map((t) => el('a', { class: 'chip line', href: `#${t}` }, tabName(t)))) : null,
      el('ol', { class: 'gd-steps' }, (d.steps || []).map((s) => el('li', {}, fillYear(s)))),
      (d.notes || []).length ? el('ul', { class: 'gd-notes' }, d.notes.map((n) => el('li', {}, fillYear(n)))) : null);
  };

  const sourceCard = (src) => {
    const documents = src.bank ? (guide.bank_documents || []) : (src.documents || []);
    const seen = seenIn(src.match);
    return el('section', { class: 'card gd-source' + (seen.length ? ' used' : '') },
      el('div', { class: 'gd-h' },
        el('div', { class: 'gd-title' },
          el('h3', {}, src.name),
          seen.length ? chip(`Seen in your folder: ${plural(seen.length, 'document')}`, 'ok') : null),
        src.url ? el('a', { class: seen.length || src.always ? 'primary' : 'ghost', href: src.url,
                            target: '_blank', rel: 'noopener noreferrer', title: src.url },
                     'Open site', icon('open')) : null),
      src.login ? el('p', { class: 'gd-login' }, icon('user'), fillYear(src.login)) : null,
      documents.map((d) => docBlock(d, src)));
  };

  const groups = guide.groups || [];
  const sources = guide.sources || [];
  const used = (s) => s.always || seenIn(s.match).length > 0;
  const section = (list) => groups.map((g) => {
    const inGroup = list.filter((s) => s.group === g.id);
    return inGroup.length ? [el('h2', { class: 'sched-group' }, g.label), el('div', { class: 'gd-grid' }, inGroup.map(sourceCard))] : null;
  }).filter(Boolean).flat();
  const mine = sources.filter(used);
  const others = sources.filter((s) => !used(s));

  const how = el('section', { class: 'card gd-how' },
    el('div', { class: 'card-body' },
      el('ol', { class: 'gd-how-steps' },
        el('li', {}, el('b', {}, 'Open the site'), ' with the button on its card, and log in. Flow never sees your password.'),
        el('li', {}, el('b', {}, 'Follow the steps'), ' on the card to download each document for ', el('b', {}, `FY ${state.fy}`), '.'),
        el('li', {}, el('b', {}, 'Save or move the file'), ' into this return’s documents folder. Sub-folders and any file name are fine.'),
        el('li', {}, el('b', {}, 'Sort documents again'), ' on the In your folder tab, then read the schedules that have new documents.')),
      el('div', { class: 'where', style: 'margin-top:12px' },
        el('div', { class: 'where-line' },
          el('span', { class: 'where-k' }, 'Documents'),
          el('span', { class: 'where-v', title: p.source_path || '' }, p.source_path || ''),
          el('button', { class: 'ghost small', type: 'button', onclick: (e) => copyText(p.source_path || '', e.currentTarget) },
             icon('copy'), 'Copy path'),
          el('button', { class: 'ghost small', type: 'button', onclick: openDocumentsFolder },
             icon('documents'), 'Open folder')))));

  return [
    el('div', { class: 'page-head' },
      el('div', {},
        el('div', { class: 'page-title' }, el('h1', {}, 'Documents')),
        el('p', { class: 'page-sub' },
          'Where each document usually comes from, and how to download it. Flow opens the site and '
          + 'shows the steps; you log in and download. Sites change their menus now and then, so if a '
          + 'step does not match, look for the nearest item with that name.'))),
    documentTabs('get', docs.length),
    how,
    mine.length ? el('h2', { class: 'gd-section' }, 'The sources you use',
      el('small', {}, 'the income-tax portal, your employer, and the sources your documents come from')) : null,
    ...section(mine),
    others.length ? el('details', { class: 'gd-more' },
      el('summary', {}, `Other common sources (${others.length})`),
      ...section(others)) : null,
  ];
}

function pageDocuments() {
  if (state.sub === 'get') return getDocumentsView();
  const ui = state.ui.documents;
  const docs = allDocuments();
  const attention = docs.filter((d) => d.state.attention);
  const q = ui.q.trim().toLowerCase();
  const list = (ui.view === 'attention' ? attention : docs)
    .filter((d) => !q || `${d.name} ${d.folder} ${d.kind}`.toLowerCase().includes(q));
  const current = docs.find((d) => d.key === state.sub) || null;
  const map = state.documentMap || {};
  const busy = routingBusy();
  const running = state.activity.running.length || Object.values(state.runs).some((r) => r.running);

  const seg = (key, label, n) => el('button', {
    type: 'button', 'aria-pressed': String(ui.view === key),
    onclick: () => { ui.view = key; renderPanel(); },
  }, label, el('span', { class: 'n' }, String(n)));
  const search = el('input', { type: 'search', placeholder: 'Filter by name or kind', value: ui.q,
                               'aria-label': 'Filter the documents' });
  search.addEventListener('input', () => {
    ui.q = search.value;
    renderPanel();
    const again = $('#panel input[type="search"]');
    again?.focus();
    again?.setSelectionRange(again.value.length, again.value.length);
  });

  const rows = list.map((d) => el('tr', {
    class: 'pick' + (current === d ? ' selected' : ''), tabindex: '0',
    onclick: () => select('documents', d.key),
    onkeydown: (e) => { if (e.key === 'Enter') select('documents', d.key); },
  },
    el('td', { class: 'desc' }, d.name,
       el('span', { class: 'src', title: d.folder || 'top folder' },
          d.folder ? (d.folder.includes('/') ? '\u2026/' : '') + baseName(d.folder) : 'top folder')),
    el('td', {}, d.kind ? clip(d.kind, 70) : el('span', { class: 'muted' }, d.unsorted ? 'Not sorted' : 'By folder rule')),
    el('td', {}, d.feeds.length
      ? el('div', { class: 'chips' },
          d.feeds.slice(0, 3).map((f) => chip(tabName(f.tab), f.read && f.noted ? 'warn' : f.read ? '' : 'line')),
          d.feeds.length > 3 ? chip(`+${d.feeds.length - 3}`) : null)
      : el('span', { class: 'muted' }, '—')),
    el('td', { class: 'nowrap' }, chip(d.state.label, d.state.tone))));

  const notes = map.notes || [];
  return [
    el('div', { class: 'page-head' },
      el('div', {},
        el('div', { class: 'page-title' }, el('h1', {}, 'Documents')),
        el('p', { class: 'page-sub' },
          'Everything in this return’s folder: what each file was recognised as, which '
          + 'schedules it feeds, and whether each of them has read it. A file nobody reads is a '
          + 'return that is wrong in a way no other page would show.')),
      el('div', { class: 'page-actions' },
        el('button', {
          class: 'primary', disabled: busy || Boolean(running),
          title: running ? 'A schedule is being read; sorting waits until that finishes.' : '',
          onclick: () => runClassify(),
        }, busy ? 'Sorting…' : 'Sort documents again'))),
    documentTabs('folder', docs.length),
    el('div', { class: 'meta-row' },
      el('span', {}, plural(docs.length, 'document')),
      map.generated_at ? el('span', { class: 'dotsep' },
        `sorted ${fmtWhen(map.generated_at)} by ${map.engine?.model || map.engine?.id || 'the engine'}`) : null,
      el('span', { class: 'dotsep' }, 'Sorting reads each file to decide what it is; it changes no figure.')),
    state.classifyLog.length
      ? el('div', { class: 'log', id: 'log-classify' }, logLines(state.classifyLog)) : null,
    attention.length ? el('div', { class: 'callout warn' }, icon('warn'),
      el('div', {}, el('b', {}, `${plural(attention.length, 'document needs', 'documents need')} attention`),
         'Either no schedule reads them, or a schedule that has been read did not include them.')) : null,
    el('div', { class: 'toolbar' },
      el('div', { class: 'seg', role: 'group', 'aria-label': 'Which documents' },
        seg('all', 'All', docs.length), seg('attention', 'Need attention', attention.length)),
      search),
    el('div', { class: 'split' },
      el('section', { class: 'card doc-table' },
        rows.length
          ? table(['Document', 'Recognised as', 'Feeds', 'State'], rows)
          : el('div', { class: 'empty-state' },
              el('h3', {}, docs.length ? 'No document matches' : 'No documents yet'),
              el('p', {}, docs.length
                ? 'Clear the filter to see every document.'
                : 'Put the year’s papers in the documents folder named on the Returns page, then sort them.'))),
      el('section', { class: 'card detail' },
        ...(current ? documentDetail(current) : [el('div', { class: 'empty-state' },
          el('h3', {}, 'Choose a document'),
          el('p', {}, 'See how it was recognised, which schedules read it, the figures taken '
                      + 'from it and what was set aside.'))]))),
    notes.length ? card(`Notes from sorting (${notes.length})`,
      el('div', { class: 'card-body' }, el('ul', { class: 'plain' }, notes.map((n) => el('li', {}, n)))),
      '', el('span', { class: 'src' }, 'observations made while sorting, for you to check')) : null,
  ];
}

/* --------------------------------------------------------------- reconcile */

const RESULT = {
  agrees: { label: 'Agrees', tone: 'ok', order: 3 },
  explained: { label: 'Explained', tone: 'info', order: 1 },
  needs: { label: 'Needs you', tone: 'warn', order: 0 },
  yours: { label: 'Yours only', tone: 'line', order: 4 },
  theirs: { label: 'Theirs only', tone: 'line', order: 5 },
};
const RESULT_OF = { matches: 'agrees', rounding: 'agrees', explained: 'explained',
                    unexplained: 'needs', not_comparable: 'theirs' };

/** One schedule's comparison with the department's record, as a list of
 *  checks. Reported lines that were added together are folded under the total
 *  they were compared on, because one broker's figure against the whole ledger
 *  means nothing. */
function reconChecks(tab) {
  const r = tab.reconciliation;
  if (!r) return [];
  const checks = [];
  const lines = r.lines || [];

  (r.groups || []).forEach((g, i) => {
    checks.push({
      id: `${tab.id}:g${i}`, tab: tab.id, label: g.label, result: RESULT_OF[g.status] || 'theirs',
      status: g.status, ours: g.ours, theirs: g.reported, difference: g.difference,
      accounted: g.accounted_by || [], unaccounted: g.unaccounted || 0,
      sub: `${plural((g.components || []).length, 'reported line')} added together`,
      parts: lines.filter((ln) => ln.status === 'component' && ln.measure === g.measure),
      rows: (g.rows || []).length,
    });
  });
  lines.forEach((ln, i) => {
    if (ln.status === 'component') return;
    const reported = ln.reported || {};
    checks.push({
      id: `${tab.id}:l${i}`, tab: tab.id, label: ln.category || 'Reported line',
      result: RESULT_OF[ln.status] || 'theirs', status: ln.status,
      ours: ln.ours ?? null, theirs: reported.amount ?? null, difference: ln.difference ?? null,
      accounted: ln.accounted_by || [], unaccounted: ln.unaccounted || 0,
      sub: [ln.code, baseName(ln.source), ln.counterparty].filter(Boolean).join(' · '),
      why: ln.why || '', cite: reported.cite || '', basis: reported.basis || '',
      source: ln.source || '', belongs: ln.belongs_to || '', rows: (ln.rows || []).length, parts: [],
    });
  });
  (r.unreported || []).forEach((m, i) => {
    checks.push({
      id: `${tab.id}:u${i}`, tab: tab.id, label: m.label, result: 'yours', status: 'unreported',
      ours: m.amount, theirs: null, difference: null, accounted: [], unaccounted: 0,
      sub: 'in your documents, with nothing reported against it',
      rows: (m.rows || []).length, parts: [],
    });
  });
  checks.sort((a, b) => RESULT[a.result].order - RESULT[b.result].order);
  return checks;
}

function reconCounts(tab) {
  const counts = { agrees: 0, explained: 0, needs: 0, yours: 0, theirs: 0 };
  reconChecks(tab).forEach((c) => { counts[c.result] += 1; });
  return counts;
}

const reconcilableTabs = () =>
  state.tabs.filter((t) => t.reconcilable && t.kind === 'extract' && t.id !== 'filed_return');

const reconNeeds = () =>
  reconcilableTabs().reduce((n, t) => n + (t.reconciliation ? reconCounts(t).needs : 0), 0);

/** "8 agree · 1 explained · 1 needs you", as chips. */
function reconChips(tab) {
  if (!tab.reconciliation) return [chip('Not compared yet', 'line')];
  const c = reconCounts(tab);
  return [
    c.needs ? chip(`${c.needs} ${c.needs === 1 ? 'needs' : 'need'} you`, 'warn') : null,
    c.agrees ? chip(`${c.agrees} ${c.agrees === 1 ? 'agrees' : 'agree'}`, 'ok') : null,
    c.explained ? chip(`${c.explained} explained`, 'info') : null,
    c.yours ? chip(`${c.yours} yours only`, 'line') : null,
    c.theirs ? chip(`${c.theirs} theirs only`, 'line') : null,
  ].filter(Boolean);
}

function logLines(entries) {
  return entries.map((e) => el('div', {},
    el('span', { class: 'ph ' + e.phase }, e.phase), el('span', {}, e.detail || '')));
}

function checkDetail(check) {
  const tab = state.tabs.find((t) => t.id === check.tab);
  const meta = RESULT[check.result];
  const body = [];
  const show = (v) => (v === null || v === undefined ? '—' : inr(v));

  body.push(el('div', { class: 'sec' },
    el('div', { class: 'versus' },
      el('div', {}, el('span', {}, 'Your documents'), el('b', {}, show(check.ours))),
      el('div', {}, el('span', {}, 'Department’s record'), el('b', {}, show(check.theirs))),
      el('div', { class: check.result === 'needs' ? 'bad' : '' },
         el('span', {}, 'Difference'), el('b', {}, show(check.difference))))));

  if (check.result === 'yours') {
    body.push(sec('Why there is nothing to set against it',
      el('p', {}, 'This figure is in the return, and no bank, broker or employer reported anything '
        + 'to the department against it. That is expected for foreign holdings, which no Indian '
        + 'source reports, and for figures a document certifies but the department’s record '
        + 'does not carry.')));
  } else if (check.result === 'theirs') {
    body.push(sec('Why it was not compared',
      el('p', {}, check.why || 'The department’s record carries this line, and this schedule '
        + 'has no figure of the same kind to set against it.'),
      check.belongs ? el('p', {}, `It belongs to ${check.belongs}.`) : null));
  } else if (check.accounted.length || check.unaccounted) {
    const total = check.accounted.reduce((a, x) => a + (x.amount || 0), 0);
    body.push(sec('What accounts for the difference',
      el('table', { class: 'sum' }, el('tbody', {},
        check.accounted.map((a) => el('tr', {},
          el('td', {}, a.what), el('td', { class: 'num' }, inr(a.amount)))),
        check.accounted.length ? el('tr', { class: 'tot' },
          el('td', {}, 'Accounted for'), el('td', { class: 'num' }, inr(total))) : null,
        el('tr', { class: check.unaccounted ? 'bad' : '' },
          el('td', {}, check.unaccounted ? 'Not accounted for' : 'Left over'),
          el('td', { class: 'num' }, inr(check.unaccounted || 0))))),
      check.unaccounted
        ? el('p', { style: 'margin-top:10px' }, 'Nothing in the documents explains this part. It is '
            + 'arithmetic, done here and not by the reading, so it cannot be explained away in words.')
        : null));
  } else if (check.result === 'agrees') {
    body.push(sec('What accounts for the difference',
      el('p', {}, check.status === 'rounding'
        ? 'The two figures differ only by rounding to whole rupees.'
        : 'The two figures are the same.')));
  }

  if (check.parts.length) {
    body.push(sec(`Item by item (${check.parts.length})`,
      el('table', { class: 'sum' }, el('tbody', {}, check.parts.map((p) => el('tr', {},
        el('td', {}, p.category,
           el('span', { class: 'why' }, [p.counterparty, baseName(p.source)].filter(Boolean).join(' · ')),
           (p.reported || {}).cite ? el('span', { class: 'src', style: 'overflow-wrap:anywhere' }, p.reported.cite) : null),
        el('td', { class: 'num' }, inr((p.reported || {}).amount))))))));
  }

  if (check.cite || check.basis) {
    body.push(sec('Where the department’s figure is from',
      check.basis ? el('p', {}, check.basis) : null,
      check.cite ? el('p', { class: 'mono', style: 'font-size:12px' }, check.cite) : null,
      check.source ? el('div', { style: 'margin-top:8px' },
        el('button', { class: 'ghost small', onclick: () => openDocument(check.source) },
           icon('open'), 'Open the document')) : null));
  }
  if (check.why && check.result !== 'theirs') body.push(sec('Note', el('p', {}, check.why)));

  const decision = check.result === 'needs'
    ? reviewItems().find((i) => i.kind === 'difference' && i.tab === check.tab && i.text.startsWith(check.label))
    : null;
  body.push(el('div', { class: 'sec', style: 'display:flex;gap:8px;flex-wrap:wrap' },
    decision ? el('a', { class: 'primary small', href: `#review/${decision.id}` },
                  decision.settled ? 'See the decision' : 'Decide this') : null,
    el('a', { class: 'ghost small', href: `#${check.tab}` }, `Open ${tabName(check.tab)}`),
    check.rows ? el('span', { class: 'muted', style: 'align-self:center;font-size:12.5px' },
                    `rests on ${plural(check.rows, 'ledger row')}`) : null));

  return [
    el('div', { class: 'detail-head' },
      el('div', { class: 'chips' }, chip(meta.label, meta.tone), chip(tabName(tab.id), 'line')),
      el('h2', {}, check.label),
      check.sub ? el('div', { class: 'why' }, check.sub) : null),
    el('div', { class: 'detail-body' }, ...body),
  ];
}

/** The comparison with the department's record, for one schedule or several.
 *  The same component serves the Reconcile page and each schedule's own
 *  Reconciliation tab, so the two can never say different things. */
function reconWorkspace(tabs) {
  const ui = state.ui.recon;
  const every = tabs.flatMap((t) => reconChecks(t));
  let current = every.find((c) => c.id === ui.check) || null;
  if (!current) current = every.find((c) => c.result === 'needs') || every[0] || null;

  // What needs you comes first; the rest keep the order of the return.
  const needing = (tab) => (tab.reconciliation && reconCounts(tab).needs ? 0 : 1);
  const ordered = tabs.slice().sort((a, b) => needing(a) - needing(b));
  const groups = ordered.map((tab) => {
    const r = tab.reconciliation;
    const run = runOf(tab.id + ':reconcile');
    const checks = reconChecks(tab);
    const hasData = Boolean(tab.document);
    const button = el('button', {
      class: r ? 'ghost small' : 'primary small',
      disabled: run.running || routingBusy() || !hasData,
      title: hasData ? '' : 'Read this schedule first; there is nothing to compare yet.',
      onclick: () => runReconcile(tab),
    }, run.running ? 'Comparing…' : r ? 'Compare again' : 'Compare now');

    const about = r?.about || {};
    const against = (r?.against || []).length
      ? (r.against.length > 3 ? `${r.against.slice(0, 3).join(', ')} and ${r.against.length - 3} more`
                              : r.against.join(', '))
      : about.against;

    const rows = checks.map((c) => el('tr', {
      class: 'pick' + (current === c ? ' selected' : ''), tabindex: '0',
      onclick: () => { ui.check = c.id; renderPanel(); },
      onkeydown: (e) => { if (e.key === 'Enter') { ui.check = c.id; renderPanel(); } },
    },
      el('td', { class: 'desc' }, c.label, c.sub ? el('span', { class: 'why' }, clip(c.sub, 90)) : null),
      el('td', { class: 'num' }, c.ours === null || c.ours === undefined ? '—' : rupees(c.ours)),
      el('td', { class: 'num' }, c.theirs === null || c.theirs === undefined ? '—' : rupees(c.theirs)),
      el('td', { class: 'nowrap' }, chip(RESULT[c.result].label, RESULT[c.result].tone))));

    return el('section', { class: 'card', style: 'margin:0 0 16px' },
      el('div', { class: 'group-head' },
        tabs.length > 1 ? el('a', { href: `#${tab.id}/reconciliation`, style: 'color:inherit;text-decoration:none' }, tabName(tab.id))
                        : el('span', {}, about.title || 'Against the department’s record'),
        ...reconChips(tab),
        el('span', { class: 'gh-end' },
          r ? el('small', {}, `compared ${fmtWhen(r.generated_at)}`) : null,
          button)),
      r && against ? el('div', { class: 'card-foot', style: 'border-top:0;border-bottom:1px solid var(--line)' },
        `Set against ${against}.`) : null,
      run.log.length ? el('div', { class: 'log', id: `log-${tab.id}:reconcile`, style: 'margin:12px 18px' },
                          logLines(run.log)) : null,
      rows.length
        ? table(['What was compared', { t: 'Your documents', num: true },
                 { t: 'Department’s record', num: true }, 'Result'], rows)
        : el('div', { class: 'empty-state' },
            el('h3', {}, hasData ? 'Not compared yet' : 'Nothing to compare yet'),
            el('p', {}, hasData
              ? 'Set this schedule beside what banks, brokers and employers reported to the '
                + 'department in the AIS, the TIS and Form 26AS.'
              : 'This schedule has not been read, so there are no figures to set against the '
                + 'department’s record.')));
  });

  return el('div', { class: 'split' },
    el('div', {}, ...groups),
    el('section', { class: 'card detail' },
      ...(current ? checkDetail(current) : [el('div', { class: 'empty-state' },
        el('h3', {}, 'Nothing compared yet'),
        el('p', {}, 'Once a schedule is compared, choose a line here to see what accounts for '
                    + 'any difference, item by item.'))])));
}

/** Why the filed return and this computation end in different places, as
 *  arithmetic that adds up to the difference. */
function causesCard(c) {
  const side = (n) => (n >= 0 ? `Payable ${inr(n)}` : `Refund ${inr(-n)}`);
  const rows = [];
  for (const cause of c.causes) {
    const head = el('tr', { class: cause.effect ? 'itemrow' : '' },
      el('td', {}, el('span', { class: 'item-label' }, cause.line), cause.label,
         cause.note ? el('span', { class: 'why' }, cause.note) : null),
      el('td', { class: 'num' }, rupees(cause.computed)),
      el('td', { class: 'num' }, rupees(cause.filed)),
      el('td', { class: 'num' + (cause.effect ? '' : ' muted') }, cause.effect ? inr(cause.effect) : 'none'));
    const kids = cause.detail.map((d) => branch(el('tr', { class: 'sub' },
      el('td', {}, el('span', { class: 'item-label' }, d.item), clip(d.label, 90),
         cause.key === 'tax' ? el('span', { class: 'why' }, 'a difference in income, which moves the tax on it') : null),
      el('td', { class: 'num' }, rupees(d.computed)),
      el('td', { class: 'num' }, rupees(d.filed)),
      el('td', { class: 'num muted' }, inr(d.difference)))));
    const trunk = branch(head, kids);
    rows.push(...trunk.rows);
    if (cause.effect && kids.length) trunk.show();
  }
  if (c.residual) {
    rows.push(el('tr', {}, el('td', {}, 'Rounding, and anything outside these four lines'),
      el('td', {}), el('td', {}), el('td', { class: 'num' }, inr(c.residual))));
  }
  rows.push(el('tr', { class: 'total' },
    el('td', {}, 'Difference in what is payable'),
    el('td', { class: 'num' }, side(c.position.computed)),
    el('td', { class: 'num' }, side(c.position.filed)),
    el('td', { class: 'num' }, inr(c.position.difference))));

  return card('Why the two differ',
    table(['Cause', { t: 'Computed here', num: true }, { t: 'Filed', num: true },
           { t: 'Effect on what is payable', num: true }], rows),
    c.position.difference ? 'warn' : '',
    el('span', { class: 'src' },
       'the form’s own arithmetic: tax, less relief, plus interest and fee, less what is already paid'));
}

function filedView() {
  const cmp = computedRegime()?.filed_comparison;
  const tab = state.tabs.find((t) => t.id === 'filed_return');
  if (!cmp) {
    const waiting = tab?.source_count && !tab.document;
    return [el('section', { class: 'card' }, el('div', { class: 'empty-state' },
      el('h3', {}, waiting ? 'The filed return has not been read yet' : 'No filed return has been supplied'),
      el('p', {}, waiting
        ? 'A document has been recognised as a filed return. Read it to set its Part B-TI, '
          + 'Part B-TTI and taxes paid beside this computation.'
        : 'Put the filed ITR among the documents and sort them again. It is used only for this '
          + 'comparison: it never feeds a figure, and never the way a figure is worked out.'),
      waiting ? el('a', { class: 'primary', href: '#filed_return' }, 'Open the filed return')
              : el('a', { class: 'ghost', href: '#documents' }, 'Go to Documents')))];
  }

  const id = cmp.identity || {};
  const facts = [id.form, id.assessment_year ? `AY ${id.assessment_year}` : null,
                 id.filed_on ? `filed ${fmtDay(id.filed_on)}` : null,
                 id.filing_section ? `under section ${id.filing_section}` : null,
                 id.revised ? 'revised return' : null].filter(Boolean);
  // Counted once: the taxes-paid lines are part of Part B-TTI and are shown
  // again under their own heading.
  const counts = ['Part B-TI', 'Part B-TTI'].map((name) => cmp.parts[name]).filter(Boolean)
    .reduce((a, p) => ({
      agrees: a.agrees + p.counts.agrees, differs: a.differs + p.counts.differs,
    }), { agrees: 0, differs: 0 });

  return [
    el('div', { class: 'callout info' }, icon('info'),
      el('div', {}, el('b', {}, facts.join(' · ') || 'Filed return'),
        'Set beside this computation, line for line. It is here to be compared with and for '
        + 'nothing else: no figure and no method in this return is taken from it. ',
        el('a', { href: '#filed_return' }, 'Open its own page'))),
    cmp.causes ? causesCard(cmp.causes) : null,
    ...filedComparison(cmp),
    el('div', { class: 'meta-row' },
      el('span', {}, `${counts.agrees} lines agree`),
      el('span', { class: 'dotsep' }, `${counts.differs} differ`),
      el('span', { class: 'dotsep' }, 'Lines stay in the order the form prints them. An item '
        + 'holding a difference opens itself.')),
  ];
}

function pageReconcile() {
  const filed = state.sub === 'filed';
  const tabs = reconcilableTabs().filter((t) => t.document || t.reconciliation || t.source_count);
  const cmp = computedRegime()?.filed_comparison;
  const compared = tabs.filter((t) => t.reconciliation).length;
  const needs = reconNeeds();

  return [
    el('div', { class: 'page-head' },
      el('div', {},
        el('div', { class: 'page-title' }, el('h1', {}, 'Reconcile')),
        el('p', { class: 'page-sub' },
          'Your documents set beside the records they should agree with. Every difference gets a '
          + 'verdict: it agrees, it is explained by arithmetic that adds up, it is on one side '
          + 'only, or nothing accounts for it and it needs you.'))),
    el('div', { class: 'toolbar' },
      el('div', { class: 'seg', role: 'group', 'aria-label': 'Reconcile against' },
        el('a', { href: '#reconcile', 'aria-current': String(!filed) }, 'Department’s record',
           needs ? el('span', { class: 'n' }, `${needs} ${needs === 1 ? 'needs' : 'need'} you`) : null),
        el('a', { href: '#reconcile/filed', 'aria-current': String(filed) }, 'Filed return',
           cmp ? el('span', { class: 'n' }, `${filedDiffers(cmp)} differ`) : null)),
      el('span', { class: 'grow' }),
      filed ? null : el('span', { class: 'muted', style: 'font-size:12.5px' },
        `${compared} of ${tabs.length} schedules compared with the AIS, the TIS and Form 26AS`)),
    ...(filed ? filedView() : [tabs.length ? reconWorkspace(tabs)
      : el('section', { class: 'card' }, el('div', { class: 'empty-state' },
          el('h3', {}, 'Nothing to reconcile yet'),
          el('p', {}, 'Once a schedule has been read it can be set against the department’s record.')))]),
  ];
}

/* ---------------------------------------------------------------- hand-off */

const rowKey = (sheet, row) => `${sheet.id}|${row.key}`;
const rowStamp = (row) => (row.values || []).map((v) => (v === null || v === undefined ? '' : String(v))).join('|');

/** 'entered', 'changed' (entered, and the figure has moved since) or ''. */
function rowState(sheet, row) {
  const mark = (state.handoff?.entered || {})[rowKey(sheet, row)];
  if (!mark) return '';
  return mark.stamp === rowStamp(row) ? 'entered' : 'changed';
}

function sheetStats(sheet) {
  const rows = sheet.rows.filter((r) => r.kind !== 'head');
  return {
    rows: rows.length,
    entered: rows.filter((r) => rowState(sheet, r) === 'entered').length,
    changed: rows.filter((r) => rowState(sheet, r) === 'changed').length,
  };
}

async function markRows(sheet, rows, entered) {
  try {
    const res = await api('/api/handoff', {
      method: 'POST',
      body: JSON.stringify({
        ay: state.ay, entered,
        rows: rows.map((r) => ({ key: rowKey(sheet, r), stamp: rowStamp(r) })),
      }),
    });
    state.handoff.entered = (await res.json()).entered;
    renderRail();
    renderPanel();
  } catch (err) {
    toast(err.message, 'err');
  }
}

function sheetCsv(sheets) {
  const out = [];
  for (const sheet of sheets) {
    out.push([sheet.title].map(csvCell).join(','));
    out.push(['Line', 'Particulars', ...sheet.columns.map((c) => c.t)].map(csvCell).join(','));
    for (const row of sheet.rows) {
      out.push([row.item, row.label, ...row.values].map(csvCell).join(','));
    }
    out.push('');
  }
  return out.join('\r\n');
}

function recordOfChanges() {
  const entries = [];
  for (const tab of state.tabs) {
    for (const o of tab.document?.overrides_applied || []) {
      entries.push({
        at: o.at, kind: 'Correction', where: tabName(tab.id),
        what: `${rupees(o.was)} corrected to ${rupees(o.value)}`
            + (o.state === 'stale' ? ' (the document now agrees)' : o.state === 'orphaned' ? ' (no longer applies)' : ''),
        detail: o.pointer, reason: o.reason,
      });
    }
  }
  for (const e of state.decisions?.log || []) {
    if (e.action === 'reopen') {
      entries.push({ at: e.at, kind: 'Reopened', where: '', what: 'A decision was reopened', reason: e.reason || '' });
    } else {
      entries.push({
        at: e.at, kind: 'Decision', where: state.tabs.some((t) => t.id === e.tab) ? tabName(e.tab) : 'Documents',
        what: e.choice_label, detail: clip(e.text, 200), reason: e.reason,
      });
    }
  }
  entries.sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')));
  return entries;
}

/** Write the workbook now, whatever the profile's setting. */
async function exportExcel() {
  try {
    const out = await api('/api/export', { method: 'POST', body: JSON.stringify({ ay: state.ay }) });
    toast(`Workbook written, ${plural((out.sheets || []).length, 'sheet', 'sheets')}: ${out.path}`);
  } catch (err) {
    toast(err.message, 'err');
  }
  await refresh();
}

function pageHandoff() {
  const sheets = state.handoff?.sheets || [];
  const stats = new Map(sheets.map((s) => [s.id, sheetStats(s)]));
  const total = [...stats.values()].reduce((a, s) => ({
    rows: a.rows + s.rows, entered: a.entered + s.entered, changed: a.changed + s.changed,
  }), { rows: 0, entered: 0, changed: 0 });
  const sheet = sheets.find((s) => s.id === state.sub) || sheets[0] || null;
  const open = openDecisions().length;
  const needs = reconNeeds();
  const changes = recordOfChanges();

  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('div', { class: 'page-title' }, el('h1', {}, 'Hand-off')),
      el('p', { class: 'page-sub' },
        'This tool files nothing. These are the figures as the return asks for them, to be '
        + 'typed into the e-filing utility, where interest under sections 234A, 234B and 234C '
        + 'and the final validations are done. Tick each line as you enter it.')),
    el('div', { class: 'page-actions no-print' },
      el('button', { class: 'ghost', disabled: !sheets.length, onclick: exportExcel,
                     title: state.export?.path || '' },
         icon('download'), 'Export to Excel'),
      el('button', { class: 'ghost', disabled: !sheets.length,
                     onclick: () => download(`flow-AY${state.ay}-every-sheet.csv`, sheetCsv(sheets), 'text/csv') },
         icon('download'), 'Every sheet as CSV'),
      el('button', { class: 'ghost', disabled: !state.tabs.find((t) => t.id === 'summary')?.document,
                     onclick: () => download(`flow-AY${state.ay}-computation.json`,
                       JSON.stringify(state.tabs.find((t) => t.id === 'summary').document, null, 2),
                       'application/json') },
         icon('download'), 'Computation as JSON')));

  // Where the workbook is and how fresh it is, so nobody sends a stale one.
  const x = state.export;
  const book = x && sheets.length ? el('div', { class: 'callout' + (x.error ? ' warn' : '') },
    icon(x.error ? 'warn' : 'download'),
    el('div', {},
      el('b', {}, x.error ? 'The Excel workbook is out of date' : 'Excel workbook'),
      x.error
        ? x.error
        : x.exists
          ? `Written ${fmtWhen(x.written_at)}`
            + (x.mode === 'auto' ? ', and rewritten after every computation. '
                                 : '. It is rewritten only when you press Export to Excel, so export again after a change. ')
          : (x.mode === 'auto' ? 'It will be written at the next computation, or export it now. '
                               : 'Not written yet. Press Export to Excel to write it. '),
      el('span', { class: 'src', style: 'display:block;margin-top:2px' }, x.path))) : null;

  if (!sheet) {
    return [head, el('section', { class: 'card' }, el('div', { class: 'empty-state' },
      el('h3', {}, 'Nothing to hand over yet'),
      el('p', {}, 'Once schedules have been read and the computation run, each appears here as '
                  + 'a sheet to copy from.')))];
  }

  const warn = (open || needs || total.changed) ? el('div', { class: 'callout warn' }, icon('warn'),
    el('div', {},
      el('b', {}, total.changed
        ? `${plural(total.changed, 'line has', 'lines have')} changed since you entered ${total.changed === 1 ? 'it' : 'them'}`
        : 'These figures may still change'),
      [open ? `${plural(open, 'decision is', 'decisions are')} still open` : null,
       needs ? `${plural(needs, 'difference from the department’s record needs', 'differences from the department’s record need')} you` : null]
        .filter(Boolean).join(', and ') || 'Each changed line is marked on its sheet.',
      (open || needs) ? '. Nothing here is locked; a line already entered is flagged if its figure moves. ' : ' ',
      open ? el('a', { href: '#review' }, 'Open Review') : null)) : null;

  const list = el('section', { class: 'card sheet-list no-print' },
    el('div', { class: 'card-body', style: 'border-bottom:1px solid var(--line)' },
      el('div', { style: 'display:flex;justify-content:space-between;font-size:13px;margin-bottom:8px' },
        el('b', {}, 'Entered'),
        el('span', { class: 'muted' }, `${total.entered} of ${total.rows} lines`)),
      el('div', { class: 'progress', role: 'progressbar', 'aria-valuemin': '0',
                  'aria-valuemax': String(total.rows), 'aria-valuenow': String(total.entered) },
        el('span', { style: `width:${total.rows ? (total.entered / total.rows * 100).toFixed(1) : 0}%` }))),
    el('div', { class: 'rows' }, sheets.map((s) => {
      const st = stats.get(s.id);
      return el('a', { class: 'row' + (s === sheet ? ' selected' : ''), href: `#handoff/${s.id}` },
        el('div', { class: 'row-main' },
          el('div', { class: 'row-t', style: '-webkit-line-clamp:1' }, s.title.split(':')[0]),
          el('div', { class: 'row-sub' }, s.title.includes(':') ? s.title.split(':').slice(1).join(':').trim() : '')),
        st.changed ? chip(`${st.changed} changed`, 'warn')
          : st.entered === st.rows ? chip('Entered', 'ok')
          : el('span', { class: 'muted', style: 'font-size:12.5px;font-variant-numeric:tabular-nums' },
               `${st.entered}/${st.rows}`));
    })));

  const st = stats.get(sheet.id);
  const enterable = sheet.rows.filter((r) => r.kind !== 'head');
  const numeric = sheet.columns.map((c) => Boolean(c.num));
  const copyValue = (row) => row.values.filter((v, i) => numeric[i] && v !== null && v !== undefined).join('\t');

  const rows = sheet.rows.map((row) => {
    if (row.kind === 'head') {
      return el('tr', { class: 'head' }, el('td', {}),
        el('td', { colspan: String(sheet.columns.length + 2) }, row.label), el('td', {}));
    }
    const status = rowState(sheet, row);
    const was = status === 'changed' ? (state.handoff.entered[rowKey(sheet, row)].stamp || '') : '';
    const copy = el('button', { class: 'copy-btn', type: 'button', title: 'Copy the figure, without commas',
                                'aria-label': `Copy ${row.item} ${row.label}`,
                                onclick: () => copyText(copyValue(row), copy) }, icon('copy', ''));
    return el('tr', { class: [row.kind === 'total' ? 'total' : row.kind === 'sub' ? 'sub' : '', status].join(' ').trim() },
      el('td', { class: 'tick' },
        el('input', { type: 'checkbox', checked: status === 'entered',
                      'aria-label': `Entered: ${row.item} ${row.label}`,
                      onchange: (e) => markRows(sheet, [row], e.target.checked) })),
      el('td', { class: 'ln' }, row.item),
      el('td', { class: 'desc' }, row.label,
        status === 'changed'
          ? el('span', { class: 'why', style: 'color:inherit;font-weight:600' },
               `Changed since you entered it. It was ${was.split('|').filter(Boolean)
                 .map((v) => (/^-?\d+$/.test(v) ? rupees(Number(v)) : v)).join(', ') || 'blank'}. `
               + 'Enter the new figure, then tick it again.')
          : null),
      ...row.values.map((v, i) => el('td', { class: numeric[i] ? 'num' : '' },
        v === null || v === undefined ? '' : numeric[i] && typeof v === 'number' ? rupees(v) : String(v))),
      el('td', { class: 'copy no-print' }, copyValue(row) ? copy : null));
  });

  const copyAll = el('button', { class: 'ghost small', type: 'button', onclick: () =>
    copyText(sheet.rows.map((r) => [r.item, r.label, ...r.values.map((v) => v ?? '')].join('\t')).join('\n'), copyAll),
  }, icon('copy'), 'Copy the sheet');

  const detail = el('section', { class: 'card sheet' },
    el('h2', {}, sheet.title,
      el('span', { class: 'asides no-print' },
        el('a', { class: 'linkish', href: `#${sheet.tab}` }, `Open ${tabName(sheet.tab)}`),
        copyAll,
        el('button', { class: 'ghost small', type: 'button',
                       onclick: () => download(`flow-AY${state.ay}-${sheet.id}.csv`, sheetCsv([sheet]), 'text/csv') },
           icon('download'), 'CSV'),
        el('button', { class: 'ghost small', type: 'button', onclick: () => window.print() }, 'Print'),
        el('button', { class: 'ghost small', type: 'button',
                       onclick: () => markRows(sheet, enterable, st.entered !== st.rows) },
           st.entered === st.rows ? 'Untick all' : 'Tick all as entered'))),
    table([{ t: el('span', { class: 'sr' }, 'Entered') }, 'Line', 'Particulars',
           ...sheet.columns.map((c) => ({ t: c.t, num: c.num })), { t: el('span', { class: 'sr' }, 'Copy') }], rows),
    sheet.note ? el('div', { class: 'card-foot' }, sheet.note) : null);

  const shown = changes.slice(0, 12);
  const record = card(`Record of changes (${changes.length})`,
    changes.length
      ? table(['When', 'What', 'Why'], shown.map((c) => el('tr', {},
          el('td', { class: 'nowrap muted' }, fmtWhen(c.at)),
          el('td', {}, el('b', {}, c.kind), c.where ? ` · ${c.where}` : '',
             el('span', { class: 'why' }, c.what),
             c.detail ? el('span', { class: 'src', style: 'overflow-wrap:anywhere' }, c.detail) : null),
          el('td', {}, c.reason || el('span', { class: 'muted' }, 'no reason recorded')))))
      : el('div', { class: 'card-body empty' },
          'No figure has been corrected and no decision settled. Each one will be listed here '
          + 'with its reason: this is what you would show someone who asks why the return says what it says.'),
    '', el('span', { class: 'src' },
      changes.length > shown.length ? `the latest ${shown.length}; the whole record is in the data folder`
                                    : 'every correction and every decision, with its reason'));

  return [head, warn, book,
    el('div', { class: 'split handoff-split' }, list, detail),
    record];
}

/* ---------------------------------------------------------------- overview */

const STATEMENT_TI = [
  ['1', 'Salaries', 'salary'], ['2', 'House property', 'house_property'],
  ['3v', 'Business or profession', 'business_computation'], ['4e', 'Capital gains', 'capital_gains'],
  ['5d', 'Other sources', 'other_sources'], ['10', 'Gross total income', 'summary', 'total'],
  ['12c', 'Less: deductions under Chapter VI-A', 'deductions'], ['14', 'Total income', 'summary', 'total'],
];
const STATEMENT_TTI = [
  ['2a', 'Tax at normal rates', 'summary'], ['2b', 'Tax at special rates', 'summary'],
  ['2e', 'Less: rebate under section 87A', 'summary', 'ifany'], ['2giv', 'Surcharge', 'summary'],
  ['2h', 'Health and education cess', 'summary'], ['2i', 'Gross tax liability', 'summary', 'total'],
  ['6d', 'Less: relief for tax paid abroad', 'foreign_special'], ['7', 'Net tax liability', 'summary', 'total'],
  ['8e', 'Interest and fee', 'summary', 'ifany'], ['10e', 'Less: taxes already paid', 'taxes_paid'],
];

function statementCard(title, code, lines, cmp) {
  const filed = new Map(((cmp?.parts || {})[code]?.rows || []).map((r) => [String(r.item), r]));
  const rows = lines.map(([item, text, tabId, kind]) => {
    const value = partLine(code, item);
    if (value === null || (kind === 'ifany' && !value)) return null;
    const other = filed.get(item);
    return el('tr', {
      class: 'go' + (kind === 'total' ? ' total' : ''), tabindex: '0', title: `Open ${tabName(tabId)}`,
      onclick: () => select(tabId),
      onkeydown: (e) => { if (e.key === 'Enter') select(tabId); },
    },
      el('td', { class: 'ln' }, item),
      el('td', {}, text),
      el('td', { class: 'num' }, rupees(Math.abs(value)),
        (item === '11' || item === '12') && cmp?.causes && cmp.causes.position.difference
          ? el('span', { class: 'filed-note' },
               cmp.causes.position.filed >= 0 ? `filed: payable ${rupees(cmp.causes.position.filed)}`
                                              : `filed: refund ${rupees(-cmp.causes.position.filed)}`)
          : other && other.state === 'differs'
            ? el('span', { class: 'filed-note' }, `filed ${rupees(Math.abs(other.filed))}`) : null));
  }).filter(Boolean);
  return card(title, table(null, rows), 'stmt');
}

/** The profile being worked in: who, which year, how it is set up, where its
 *  files are. Read-only here; it is changed under Returns and profiles. */
function profileCard() {
  const p = state.activeProfile || {};
  const settings = p.settings || {};
  const fields = state.profileFields || {};
  const chosen = (key) => {
    const value = settings[key] ?? fields[key]?.default;
    return (fields[key]?.options || []).find((o) => o.value === value)?.label || '';
  };
  // Enough of the PAN to know it is the right one, without it sitting in
  // full on the first screen anyone looks at.
  const pan = p.pan ? `${p.pan.slice(0, 3)}\u2022\u2022\u2022\u2022${p.pan.slice(-3)}` : '';
  const docs = allDocuments().length;
  const x = state.export;
  const engine = (state.engines || []).find((e) => e.id === engineId());
  const fact = (k, v, cls = '') => (v ? el('div', { class: 'fact-row' },
    el('dt', {}, k), el('dd', { class: cls, title: cls ? String(v) : null }, v)) : null);
  const group = (title, ...rows) => el('div', { class: 'fact-group' },
    el('h3', {}, title), el('dl', {}, rows));
  return card(`Return: ${p.name || ''}`,
    el('div', { class: 'card-body facts' },
      group('The return',
        fact('Financial year', state.fy),
        fact('Assessment year', state.ay),
        fact('Form', 'ITR-3'),
        fact('PAN', pan || el('a', { href: '#_profiles' }, 'not entered')),
        fact('Residential status', 'Resident and ordinarily resident')),
      group('How it is computed',
        fact('Regime', chosen('regime')),
        fact('Age', chosen('age_band')),
        fact('Tax audit', chosen('audit_44ab')),
        fact('Date of birth', settings.dob || el('a', { href: '#_profiles' }, 'not entered')),
        fact('Reading engine', engine ? `${engine.label}${engine.available ? '' : ' (not found)'}` : 'none found')),
      group('Where its files are',
        fact('Documents', p.source_path, 'path'),
        fact('', `${plural(docs, 'document')} in it`),
        fact('Results', p.data_path, 'path'),
        fact('Excel workbook', x ? (x.exists ? `written ${fmtWhen(x.written_at)}` : 'not written yet') : ''))),
    'profile-card', el('a', { class: 'linkish', href: '#_profiles' }, 'Change in Returns'));
}

function pageOverview() {
  const summary = state.tabs.find((t) => t.id === 'summary')?.document;
  const regime = computedRegime();
  const totals = regime?.cascade?.totals;
  const profile = state.activeProfile || {};

  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('div', { class: 'page-title' }, el('h1', {}, 'Summary')),
      el('p', { class: 'page-sub' },
        [profile.name, `Assessment year ${state.ay}`, `financial year ${state.fy}`, 'ITR-3',
         'resident and ordinarily resident'].filter(Boolean).join(' · '))));

  if (!totals) {
    const reason = summary?.unavailable;
    return [head, profileCard(), el('section', { class: 'card' }, el('div', { class: 'empty-state' },
      el('h3', {}, reason ? 'No computation is possible for this year yet' : 'Nothing has been computed yet'),
      el('p', {}, reason || 'Put the year’s documents in the folder, sort them, and read a '
        + 'schedule. The computation follows on its own, and this page then shows where the return stands.'),
      el('div', { style: 'display:flex;gap:8px;justify-content:center' },
        el('a', { class: 'primary', href: '#documents' }, 'Go to Documents'),
        el('a', { class: 'ghost', href: '#home/start' }, 'Getting started'))))];
  }

  const items = reviewItems();
  const open = items.filter((i) => i.counts && !i.settled);
  const aside = items.filter((i) => !i.counts && !i.settled);
  const settledCount = items.filter((i) => i.settled).length;
  const docs = allDocuments();
  const attention = docs.filter((d) => d.state.attention);
  const noted = docs.filter((d) => d.state.key === 'noted').length;
  const cmp = regime.filed_comparison;
  const reconTabs = reconcilableTabs().filter((t) => t.document);
  const compared = reconTabs.filter((t) => t.reconciliation);
  const needs = reconNeeds();
  const sheets = state.handoff?.sheets || [];
  const entered = sheets.reduce((a, s) => {
    const st = sheetStats(s);
    return { rows: a.rows + st.rows, entered: a.entered + st.entered, changed: a.changed + st.changed };
  }, { rows: 0, entered: 0, changed: 0 });
  const scheduleTabs = state.tabs.filter((t) => t.kind !== 'derive' && t.id !== 'filed_return');
  const read = scheduleTabs.filter((t) => t.document);
  const empty = scheduleTabs.filter((t) => !t.document && !t.source_count);
  const waiting = scheduleTabs.filter((t) => !t.document && t.source_count);
  const notIncluded = (summary.not_implemented || []).length;

  const refund = totals.refund > 0;
  const regimeName = summary.recommended_regime === 'new' ? 'New regime, section 115BAC(1A)' : 'Old regime';
  const regimeNote = summary.regime_is_elected
    ? (summary.election_costs
        ? `as elected. The other regime would cost ${inr(summary.election_costs)} less.`
        : `as elected. It is also the cheaper of the two, by ${inr(summary.saving_versus_other)}.`)
    : `the cheaper of the two, by ${inr(summary.saving_versus_other)}.`;

  const need = (g, text, sub, href) => el('li', {},
    el('a', { href }, glyph(g, ''), el('span', {}, text, sub ? el('small', {}, sub) : null)));
  const needsList = [
    open.length ? need('open', `${plural(open.length, 'decision')} to make`,
      'questions the documents do not answer, and differences nothing accounts for', '#review') : null,
    attention.length ? need('open', `${plural(attention.length, 'document needs', 'documents need')} attention`,
      'not read, or read by no schedule', '#documents') : null,
    waiting.length ? need('wait', `${plural(waiting.length, 'schedule has', 'schedules have')} documents waiting`,
      waiting.map((t) => tabName(t.id)).join(', '), `#${waiting[0].id}`) : null,
    notIncluded ? need('empty', `${plural(notIncluded, 'thing is', 'things are')} not in these figures`,
      'listed on the Computation page; read them before relying on the balance', '#summary') : null,
  ].filter(Boolean);

  const hero = el('section', { class: 'hero' },
    el('div', { class: 'hero-main' },
      el('div', { class: 'hero-cap' }, refund ? 'Refund due' : 'Balance payable'),
      el('div', { class: 'hero-n' + (refund ? ' refund' : '') },
        el('span', { class: 'cur' }, '₹'), rupees(refund ? totals.refund : totals.payable)),
      el('p', { class: 'hero-note' },
        'Net tax of ', el('b', {}, inr(totals.net_tax_liability)), ' less ',
        el('b', {}, inr(totals.taxes_paid)), ' already paid. ',
        `${regimeName}, ${regimeNote}`),
      el('div', { class: 'hero-meta' },
        `Computed ${fmtWhen(summary.computed_at)} · a draft for review, not a filing`)),
    el('div', { class: 'hero-side' },
      el('h3', {}, 'Before you rely on this'),
      needsList.length
        ? el('ul', { class: 'needs' }, ...needsList)
        : el('ul', { class: 'needs' }, el('li', {}, el('a', { href: '#handoff' }, glyph('ok', ''),
            el('span', {}, 'Nothing is waiting on you', el('small', {}, 'the figures are ready to hand over')))))));

  /* ---- the return in a few ratios and pictures ---------------------------
     Every figure below is a line of Part B-TI or Part B-TTI, or one divided
     by another; the two statements further down are the same numbers as a
     table. */
  const ti = (item) => partLine('Part B-TI', item) ?? 0;
  const tti = (item) => partLine('Part B-TTI', item) ?? 0;
  const gti = totals.gross_total_income;
  const netTax = totals.net_tax_liability;
  const paidAtSource = tti('10b') + tti('10c');
  const salaryHead = regime.heads?.salary || {};
  const via = regime.chapter_via?.total_allowed || 0;
  const slices = (regime.cascade.stages || []).find((s) => s.code === 'Schedule SI') || {};
  const specials = (slices.table?.rows || []).filter((r) => r[5] !== 'slab' && r[1]);
  const exemptGains = specials.reduce((a, r) => a + (r[2] || 0), 0);
  const keptOut = [
    ['standard deduction and other section 16 deductions', salaryHead.deductions_16 || 0],
    ['exempt allowances', salaryHead.exempt || 0],
    ['Chapter VI-A', via],
    ['exempt long-term gains under section 112A', exemptGains],
  ].filter(([, v]) => v > 0);
  const keptOutTotal = keptOut.reduce((a, [, v]) => a + v, 0);

  const other = summary.recommended_regime === 'new' ? 'old' : 'new';
  const otherTax = summary.regimes?.[other]?.cascade?.totals?.net_tax_liability;
  const regimeWord = (r) => (r === 'new' ? 'New regime' : 'Old regime');
  const regimeTile = typeof otherTax === 'number' ? statTile(
    'The two regimes',
    netTax === otherTax ? 'No difference'
      : `${inr(Math.abs(otherTax - netTax))} ${netTax < otherTax ? 'saved' : 'more'}`,
    netTax === otherTax ? 'Both regimes come to the same tax.'
      : `by the ${summary.recommended_regime} regime this return is computed under, against the ${other}.`,
    barList([
      { label: regimeWord(summary.recommended_regime), value: netTax, tip: 'net tax liability, this return' },
      { label: regimeWord(other), value: otherTax, tone: 'quiet', tip: 'net tax liability, had it been chosen' },
    ])) : null;

  const tiles = el('section', { class: 'tiles' },
    statTile('Effective tax rate', gti > 0 ? pct(netTax / gti, 2) : '—',
      `${inr(netTax)} of tax on ${inr(gti)} of gross total income.`),
    statTile('Marginal rate', regime.marginal_rate ? pct(regime.marginal_rate, 2) : '—',
      regime.marginal_rate
        ? `What the next ₹100 of ordinary income costs: ₹${(regime.marginal_rate * 100).toFixed(2)}, `
          + 'slab rate with surcharge and cess.'
        : 'No tax falls on the next rupee of ordinary income.'),
    statTile('Income after tax', inr(gti - netTax),
      `Gross total income less the tax on it: about ${inr(Math.round((gti - netTax) / 12))} a month.`),
    statTile('Tax already paid', netTax > 0 ? pct(Math.min(totals.taxes_paid / netTax, 9.99), 1) : '—',
      netTax > 0
        ? `${inr(totals.taxes_paid)} of ${inr(netTax)}`
          + (totals.taxes_paid ? `; ${pct(paidAtSource / totals.taxes_paid, 0)} of it deducted or collected at source.` : '.')
        : 'No tax is due on this income.'),
    statTile('Kept out of tax', inr(keptOutTotal),
      keptOut.length
        ? `Deductions and exemptions used: ${keptOut.map(([what, v]) => `${what} ${inr(v)}`).join(', ')}.`
        : 'No deduction or exemption reduces this income.'),
    regimeTile);

  const headRows = [['1', 'Salary', 'salary'], ['2', 'House property', 'house_property'],
                    ['3v', 'Business or profession', 'business_computation'],
                    ['4e', 'Capital gains', 'capital_gains'], ['5d', 'Other sources', 'other_sources']]
    .map(([item, label, tabId]) => ({ item, label, tabId, value: ti(item) }))
    .filter((h) => h.value || state.tabs.find((t) => t.id === h.tabId)?.document);
  const headsTotal = headRows.reduce((a, h) => a + Math.max(0, h.value), 0);
  const incomeChart = card('Where the income comes from',
    el('div', { class: 'card-body' },
      barList(headRows.map((h) => ({
        label: h.label, value: h.value, href: `#${h.tabId}`, sub: `line ${h.item}`,
        share: headsTotal && h.value > 0 ? pct(h.value / headsTotal) : '',
        tip: `Part B-TI line ${h.item}. Open ${tabName(h.tabId)}.` }))),
      el('p', { class: 'viz-note' },
        'Gross total income ', el('b', {}, inr(gti)),
        via ? [', less ', el('b', {}, inr(via)), ' under Chapter VI-A'] : null,
        ': total income ', el('b', {}, inr(totals.total_income)), '.')),
    'viz', el('span', { class: 'src' }, 'each head, after its own deductions'));

  const ladder = slices.ladder || [];
  const slabIncome = totals.slab_income;
  const slabCard = ladder.length ? card('How the ordinary income is taxed',
    el('div', { class: 'card-body' },
      slabChart(ladder),
      el('p', { class: 'viz-note' },
        'Each column is one slab band: as wide as the income in it, as tall as its rate. ',
        el('b', {}, inr(slabIncome)), ' of ordinary income bears ', el('b', {}, inr(totals.tax_at_slab)),
        ', an average of ', el('b', {}, slabIncome ? pct(totals.tax_at_slab / slabIncome, 2) : '—'),
        ` against ${pct(ladder[ladder.length - 1].rate, 2)} on the last rupee. Surcharge and cess come on top.`,
        specials.length ? ` Taxed apart from the ladder: ${specials.map((r) => (r[4]
          ? `${r[0]} ${inr(r[1])}, of which ${inr(r[4])} is taxed at ${r[5]}: ${inr(r[6])}`
          : `${r[0]} ${inr(r[1])}, none of it taxed because it is within the exemption`)).join('; ')}.` : ''),
      el('details', { class: 'viz-table' }, el('summary', {}, 'As a table'),
        table([{ t: 'Band' }, { t: 'Income in it', num: true }, { t: 'Rate', num: true }, { t: 'Tax', num: true }],
          ladder.map((b) => el('tr', {},
            el('td', {}, `${inr(b.from)} to ${inr(b.to)}`),
            el('td', { class: 'num' }, rupees(b.amount)),
            el('td', { class: 'num' }, pct(b.rate, 2)),
            el('td', { class: 'num' }, rupees(b.tax))))))),
    'viz', el('a', { class: 'linkish', href: '#summary' }, 'Open Computation')) : null;

  const taxParts = [
    { label: 'Tax at normal rates', value: tti('2a'), sub: 'line 2a' },
    { label: 'Tax at special rates', value: tti('2b'), sub: 'line 2b' },
    { label: 'Rebate under section 87A', value: -tti('2e'), sub: 'line 2e' },
    { label: 'Surcharge', value: tti('2giv'), sub: 'line 2giv' },
    { label: 'Health and education cess', value: tti('2h'), sub: 'line 2h' },
    { label: 'Relief for tax paid abroad', value: -tti('6d'), sub: 'line 6d' },
    { label: 'Interest and fee', value: tti('8e'), sub: 'line 8e' },
  ].filter((p) => p.value).map((p) => ({ ...p, href: '#summary',
    share: netTax && p.value > 0 ? pct(p.value / netTax) : '', tip: `Part B-TTI ${p.sub}` }));
  const taxChart = card('What the tax is made of',
    el('div', { class: 'card-body' },
      taxParts.length ? barList(taxParts) : el('div', { class: 'empty' }, 'No tax arises on this income.'),
      el('p', { class: 'viz-note' }, 'Net tax liability ', el('b', {}, inr(netTax)),
        tti('8e') ? [', and with interest and fee ', el('b', {}, inr(tti('9')))] : null, '.')),
    'viz', el('span', { class: 'src' }, 'shares are of the net tax'));

  const liability = tti('9') || netTax;
  const payChart = card('How the tax is being paid',
    el('div', { class: 'card-body' },
      el('div', { class: 'meter-head' },
        el('b', {}, liability ? pct(Math.min(totals.taxes_paid / liability, 9.99), 1) : '—'),
        el('span', {}, ` paid: ${inr(totals.taxes_paid)} of ${inr(liability)}`)),
      payMeter([
        { label: 'Tax deducted at source', value: tti('10b'), href: '#taxes_paid' },
        { label: 'Tax collected at source', value: tti('10c'), href: '#taxes_paid' },
        { label: 'Advance tax', value: tti('10a'), href: '#taxes_paid' },
        { label: 'Self-assessment tax', value: tti('10d'), href: '#taxes_paid' },
      ], liability),
      el('p', { class: 'viz-note' }, refund
        ? 'More was paid than is due; the difference comes back as a refund.'
        : 'What is still to pay is settled as self-assessment tax before filing. Interest under '
          + 'sections 234A, 234B and 234C is not in these figures.')),
    'viz', el('a', { class: 'linkish', href: '#taxes_paid' }, 'Open Taxes paid'));

  const areaRow = (iconName, title, href, done, total, ...status) => el('a', { class: 'area-row', href },
    icon(iconName), el('b', {}, title), el('span', { class: 'area-s' }, ...status),
    miniMeter(done, total), icon('chev', 'ico chev'));
  const warnText = (text) => el('span', { class: 'warn' }, text);
  const join = (parts) => parts.filter(Boolean).flatMap((p, i) => (i ? [' · ', p] : [p]));

  const areas = card('By area',
    el('div', {},
      areaRow('documents', 'Documents', '#documents', docs.length - attention.length, docs.length, ...join([
        plural(docs.length, 'document'),
        attention.length ? warnText(`${attention.length} need attention`) : 'every one read or accounted for',
        noted ? `${noted} read with a note` : null])),
      areaRow('calc', 'Schedules', '#schedules',
              read.length, read.length + waiting.length, ...join([
        `${read.length} of ${scheduleTabs.length} read`,
        waiting.length ? warnText(`${waiting.length} waiting to be read`) : null,
        empty.length ? `${empty.length} with nothing supplied` : null])),
      areaRow('review', 'Review', '#review', settledCount, settledCount + open.length, ...join([
        open.length ? warnText(`${plural(open.length, 'decision')} open`) : 'nothing open',
        aside.length ? `${aside.length} set aside to check` : null,
        settledCount ? `${settledCount} settled` : null])),
      areaRow('reconcile', 'Reconcile', '#reconcile', compared.length, reconTabs.length, ...join([
        `${compared.length} of ${reconTabs.length} schedules compared with the department’s record`,
        needs ? warnText(`${needs} ${needs === 1 ? 'difference needs' : 'differences need'} you`) : null,
        cmp ? `filed return: ${filedDiffers(cmp)} lines differ` : 'no filed return supplied'])),
      areaRow('handoff', 'Hand-off', '#handoff', entered.entered, entered.rows, ...join([
        `${entered.entered} of ${entered.rows} lines entered`,
        entered.changed ? warnText(`${entered.changed} changed since entered`) : null]))),
    '', el('span', { class: 'src' }, 'how far along each is; open any of them, in any order'));

  const top = open.slice(0, 5);
  const decisions = card(`Open decisions (${open.length})`,
    top.length
      ? el('div', { class: 'rows' }, ...top.map((i) => el('a', { class: 'row', href: `#review/${i.id}` },
          el('div', { class: 'row-main' },
            el('div', { class: 'row-t' }, i.text),
            el('div', { class: 'row-sub' }, chip(KIND[i.kind].label, KIND[i.kind].tone),
               el('span', {}, state.tabs.some((t) => t.id === i.tab) ? tabName(i.tab) : 'Documents'))),
          el('div', { class: 'row-end' }, typeof i.amount === 'number' && i.amount ? inr(i.amount) : ''))),
          open.length > top.length ? el('a', { class: 'row', href: '#review', style: 'color:var(--blue);font-weight:600' },
            el('div', {}, `See all ${open.length} in Review`), el('div', {})) : null)
      : el('div', { class: 'card-body empty' }, 'Nothing is waiting on a decision.'),
    open.length ? 'warn' : '',
    el('span', { class: 'src' }, 'differences first, then questions schedule by schedule'));

  // How each schedule reconciles, on the two sides it can be checked against.
  const filedRows = new Map(((cmp?.parts || {})['Part B-TI']?.rows || []).map((r) => [String(r.item), r]));
  const filedTti = new Map(((cmp?.parts || {})['Part B-TTI']?.rows || []).map((r) => [String(r.item), r]));
  const reconRows = state.tabs
    .filter((t) => (t.document || t.kind === 'derive') && HEADLINE[t.id] && t.id !== 'summary')
    .map((t) => {
      const [code, item] = HEADLINE[t.id];
      const f = (code === 'Part B-TI' ? filedRows : filedTti).get(item);
      const can = t.reconcilable && t.kind === 'extract';
      return el('tr', { class: 'pick', tabindex: '0', onclick: () => select(t.id, can ? 'reconciliation' : null),
                        onkeydown: (e) => { if (e.key === 'Enter') select(t.id, can ? 'reconciliation' : null); } },
        el('td', {}, tabName(t.id), el('span', { class: 'why' }, `${code} line ${item}`)),
        el('td', { class: 'num' }, rupees(Math.abs(partLine(code, item) ?? 0))),
        el('td', {}, can ? el('div', { class: 'chips' }, ...reconChips(t))
                         : el('span', { class: 'muted' }, 'computed from other schedules')),
        el('td', {}, !cmp ? el('span', { class: 'muted' }, '—')
          : !f ? el('span', { class: 'muted' }, 'no such line')
          : f.state === 'differs' ? chip(`Differs by ${inr(f.difference)}`, 'warn')
          : chip('Agrees', 'ok')));
    });
  const outcome = compared.reduce((a, t) => {
    const c = reconCounts(t);
    return { agrees: a.agrees + c.agrees, explained: a.explained + c.explained, needs: a.needs + c.needs,
             oneSided: a.oneSided + c.yours + c.theirs };
  }, { agrees: 0, explained: 0, needs: 0, oneSided: 0 });
  const recon = card('Reconciliation by schedule',
    el('div', {},
      compared.length ? el('div', { class: 'card-body', style: 'border-bottom:1px solid var(--line)' },
        statusBar([
          { label: outcome.agrees === 1 ? 'line agrees with the department’s record' : 'lines agree with the department’s record',
            value: outcome.agrees, tone: 'ok' },
          { label: 'differ, and the difference is accounted for', value: outcome.explained, tone: 'quiet' },
          { label: outcome.needs === 1 ? 'needs you' : 'need you', value: outcome.needs, tone: 'warn' },
        ]),
        outcome.oneSided ? el('p', { class: 'viz-note' },
          `${plural(outcome.oneSided, 'more line is', 'more lines are')} on one side only, so there is nothing to compare.`) : null) : null,
      table(['Schedule', { t: 'This return', num: true }, 'Department’s record',
             cmp ? 'Filed return' : 'Filed return (none supplied)'], reconRows)),
    needs ? 'warn' : '',
    el('a', { class: 'linkish', href: '#reconcile' }, 'Open Reconcile'));

  return [
    head, hero, profileCard(), tiles,
    el('div', { class: 'grid-2' }, incomeChart, slabCard || taxChart),
    el('div', { class: 'grid-2' }, slabCard ? taxChart : null, payChart),
    el('div', { class: 'grid-2' },
      statementCard('Income', 'Part B-TI', STATEMENT_TI, cmp),
      statementCard('Tax', 'Part B-TTI', [...STATEMENT_TTI,
        refund ? ['12', 'Refund due', 'summary', 'total'] : ['11', 'Balance payable', 'summary', 'total']], cmp)),
    areas, decisions, recon,
  ];
}

/* --------------------------------------------------------------- schedules */

// What each schedule is, in a sentence a first-time filer can follow, and the
// papers it is usually read from. Wording only: nothing is computed from this.
const SCHEDULE_ABOUT = {
  general: { about: 'Who the return is for: name, PAN, address and the bank accounts held, one of which receives any refund.',
             reads: 'Form 16, bank statements, the AIS, a PAN card' },
  salary: { about: 'What your employer paid you: salary, perquisites such as stock awards, less the standard deduction.',
            reads: 'Form 16, Form 12BA, salary slips, stock award statements' },
  house_property: { about: 'Rent from a property you let out, or the home-loan interest on one you live in.',
                    reads: 'rent agreements, home-loan interest certificates, municipal tax receipts' },
  business_computation: { about: 'The profit or loss of your business or profession for tax, worked out from the books and depreciation.',
                          reads: 'nothing of its own; computed from Books and Depreciation' },
  books: { about: 'The receipts and expenses of the business or profession, including futures and options and intraday trading.',
           reads: 'books of account, invoices, broker tax P&L, bank statements' },
  depreciation: { about: 'The allowance for wear on business assets, block by block, at the rates the rules fix.',
                  reads: 'nothing of its own; computed from the assets in Books' },
  capital_gains: { about: 'Gains and losses on selling shares, mutual funds, property and other assets, short-term and long-term.',
                   reads: 'broker capital-gains statements, tax P&L, contract notes, foreign broker statements' },
  scrip_112a: { about: 'Long-term sales of listed shares and equity funds, in the layout the return asks for them in.',
                reads: 'nothing of its own; built from the Capital gains ledger' },
  vda: { about: 'Gains on crypto and other virtual digital assets, taxed at a flat rate with no set-off.',
         reads: 'exchange statements, wallet transaction reports' },
  other_sources: { about: 'Income that fits no other head: bank and deposit interest, dividends, and the like.',
                   reads: 'interest certificates, bank statements, dividend statements, the AIS' },
  deductions: { about: 'What reduces taxable income under Chapter VI-A: NPS, insurance, donations and others, as the regime allows.',
                reads: 'Form 16, investment and premium receipts, donation receipts' },
  setoff_cfl: { about: 'Losses from earlier years brought forward to set against this year’s income, and what is carried on.',
                reads: 'last year’s return, loss schedules from earlier years' },
  summary: { about: 'The whole return worked through in order: set-offs, total income, tax on each slice, and what is left to pay.',
             reads: 'nothing of its own; computed from every schedule read' },
  taxes_paid: { about: 'Tax already paid for the year: TDS, TCS, advance tax and self-assessment tax.',
                reads: 'Form 26AS, the AIS, Form 16 Part A, challans' },
  foreign_special: { about: 'Income earned and assets held outside India, and relief for tax paid abroad. Needed by any resident with either.',
                     reads: 'foreign broker and bank statements, stock plan statements, foreign tax forms' },
  assets_liabilities: { about: 'What you own and owe at the year end. Required only when total income is above ₹50 lakh.',
                        reads: 'property papers, bank and demat statements, loan statements' },
  filed_return: { about: 'A return already filed for this year, set beside this computation line by line. It is compared, never used to compute.',
                  reads: 'the filed return’s PDF or JSON, the acknowledgement' },
};

/** The one idea that explains every button on a schedule: the engine reads,
 *  the program computes, and only reading ever needs asking for. */
function readingAndComputing() {
  const side = (iconName, title, by, points, buttons, cls = '') => el('div', { class: `rc-side ${cls}` },
    el('div', { class: 'rc-h' }, icon(iconName), el('div', {}, el('b', {}, title), el('small', {}, by))),
    el('ul', {}, points.map((t) => el('li', {}, t))),
    el('div', { class: 'rc-btns' }, el('span', {}, 'Buttons: '), buttons.map((b) => el('span', { class: 'chip line' }, b))));
  return el('section', { class: 'card rc' },
    el('h2', {}, 'Reading and computing are two different things'),
    el('div', { class: 'card-body' },
      el('div', { class: 'rc-grid' },
        side('doc', 'Reading', 'done by the AI engine',
          ['Opens your documents and copies out the facts it finds: a salary figure, each share sale, each interest credit.',
           'Does no tax arithmetic. Every fact is tied to the line it came from.',
           'Takes a minute or two a schedule and uses your AI subscription.'],
          ['Read documents', 'Read again']),
        el('div', { class: 'rc-arrow', 'aria-hidden': 'true' }, icon('chev')),
        side('calc', 'Computing', 'done by Flow itself, with no AI',
          ['Applies the tax rules to those facts: deductions, set-offs, slab rates, surcharge, cess, the balance.',
           'Instant, and the same answer every time for the same facts.',
           'Happens by itself after every reading, correction or change of setting.'],
          ['Recompute'], 'mid')),
      el('p', { class: 'viz-note' },
        el('b', {}, 'So the only thing you ever need to ask for is a reading. '),
        'Read a schedule once after sorting, and again only when you add or replace one of its documents. '
        + '“Read again” keeps your corrections and decisions. “Recompute” is there for the rare time the top bar says “Out of date”.')));
}

/** Every schedule on one page: what it is, where it stands, and its button. */
function pageSchedules() {
  const waiting = state.tabs.filter((t) => t.implemented && t.kind === 'extract' && t.source_count && !t.document);
  const busy = () => waiting.some((t) => isRunning(t.id)) || routingBusy();

  const cardFor = (id) => {
    const tab = tabOf(id);
    if (!tab) return null;
    const st = scheduleState(tab);
    const info = SCHEDULE_ABOUT[id] || {};
    const amount = headline(id);
    const d = tab.document;
    const derive = tab.kind === 'derive';
    const facts = [
      derive ? null : plural(tab.source_count || 0, 'document'),
      d ? (derive ? fmtWhen(d.resolved_at || d.generated_at) : `read ${fmtWhen(d.resolved_at || d.generated_at)}`) : null,
    ].filter(Boolean).join(' · ');
    return el('section', { class: `sched ${st.g}` },
      el('div', { class: 'sched-h' },
        glyph(st.g, ''),
        el('a', { class: 'sched-t', href: `#${id}` }, tabName(id)),
        amount !== null ? el('b', { class: 'sched-amt', title: 'the line this schedule ends up on' }, inr(amount)) : null),
      el('div', { class: 'chips' }, (tab.schedules || []).map((s) => el('span', { class: 'chip line' }, s))),
      el('p', { class: 'sched-about' }, info.about || tab.title),
      info.reads ? el('p', { class: 'sched-reads' }, el('span', {}, derive ? 'Built from: ' : 'Reads: '), info.reads) : null,
      el('div', { class: 'sched-f' },
        el('span', { class: 'sched-s' }, el('b', {}, st.text), facts ? ` · ${facts}` : ''),
        el('span', { class: 'sched-acts' },
          tab.implemented ? runAction(tab, d) : null,
          el('a', { class: 'ghost', href: `#${id}` }, 'Open'))));
  };

  const groups = [...SCHEDULE_GROUPS, { label: 'For comparison', items: [['filed_return']] }];
  const sections = groups.map((group) => {
    const cards = group.items.flatMap(([parent, kids]) => [parent, ...(kids || [])]).map(cardFor).filter(Boolean);
    return cards.length ? [el('h2', { class: 'sched-group' }, group.label), el('div', { class: 'sched-grid' }, cards)] : null;
  });

  // One after another, so the engine is not asked for everything at once.
  const readWaiting = async () => {
    for (const tab of waiting) {
      const now = tabOf(tab.id);
      if (now && !now.document && !isRunning(now.id)) await runTab(now);
    }
  };

  return [
    el('div', { class: 'page-head' },
      el('div', {},
        el('div', { class: 'page-title' }, el('h1', {}, 'Schedules')),
        el('p', { class: 'page-sub' },
          'A return is made of schedules, one for each kind of income, deduction and disclosure. '
          + 'Reading a schedule fills it in from your documents; the tax is then worked out again by itself. '
          + 'Schedules marked as built from others need no reading.')),
      el('div', { class: 'page-actions' },
        el('button', { class: 'primary', disabled: !waiting.length || busy(), onclick: readWaiting,
                       title: waiting.length ? `${waiting.map((t) => tabName(t.id)).join(', ')}, one after another`
                                             : 'Every schedule with documents has been read' },
          icon('refresh'), waiting.length ? `Read the ${waiting.length} waiting` : 'Nothing waiting to be read'))),
    readingAndComputing(),
    ...sections.filter(Boolean).flat(),
  ];
}

/* --------------------------------------------------------- getting started */

/** How to use the tool, start to finish, for someone who has never seen it.
 *
 * This page is documentation, not a status report: it says what to do, in the
 * order to do it, and where on the page each thing is. The only things it
 * takes from the return in hand are the ones a reader would otherwise have to
 * go and find -- the profile's folder paths, and whether an engine is installed.
 */
/** The guide's steps, in the order a first return is usually done. Shared by
 *  the Home page; each step says what to do and where, not how far along it is. */
function guideSteps() {
  const p = state.activeProfile || {};
  const ui = (text) => el('b', { class: 'ui' }, text);
  const pathRow = (label, path) => (path ? el('div', { class: 'where-line' },
    el('span', { class: 'where-k' }, label), el('span', { class: 'where-v', title: path }, path),
    el('button', { class: 'ghost small', type: 'button',
                   onclick: (e) => copyText(path, e.currentTarget) }, icon('copy'), 'Copy path')) : null);

  const steps = [
    { id: 'profile', icon: 'user', title: 'Set up your return',
      lead: 'A return is one person and one financial year, with its own settings and folders. Flow starts you with one called DEFAULT.',
      does: [
        ['Open ', ui('Returns'), ' at the top of the left panel.'],
        ['Fill in the ', ui('name'), ', ', ui('financial year'), ', ', ui('PAN'), ' and ', ui('date of birth'),
         '. The PAN and date of birth are what open the password-protected AIS and TIS.'],
        ['Choose the ', ui('regime'), ' (pick “Compare both” if you are not sure), your ', ui('age'),
         ' and the ', ui('reading engine'), '.'],
        ['Filing for someone else, or another year? Add another return there and switch with ',
         ui('Return'), ' at the top left.'],
      ],
      where: 'Left panel › Returns',
      go: ['Open Returns', '#_profiles'] },
    { id: 'documents', icon: 'documents', title: 'Copy your documents into the return’s folder',
      lead: 'Everything for the year goes into one folder. Flow works out what each file is, so nothing needs sorting or renaming.',
      does: [
        ['Open the documents folder below in File Explorer and copy your files into it. Sub-folders are fine.'],
        ['Not sure where to get something? ', ui('Documents › Get documents'),
         ' opens each site (income-tax portal, brokers, banks, stock plans) and says exactly what to download.'],
        ['Put in: ', ui('Form 16'), ' and Form 12BA; the ', ui('AIS'), ', ', ui('TIS'), ' and ', ui('Form 26AS'),
         ' from the income-tax portal; broker statements (capital gains, tax P&L, dividends); bank statements and interest certificates.'],
        ['If they apply: business books and invoices, foreign share statements, proofs for deductions, and last year’s filed return to compare against.'],
      ],
      extra: () => el('div', { class: 'where' }, pathRow('Documents', p.source_path)),
      where: 'On your computer, or Documents › Get documents',
      go: ['Open Get documents', '#documents/get'] },
    { id: 'sort', icon: 'sort', title: 'Sort the documents',
      lead: 'Flow opens every file, decides what it is, and sends it to the schedules that need it.',
      does: [
        ['Open ', ui('Documents'), ' in the left panel and press ', ui('Sort documents again'), '. It takes a minute or two.'],
        ['Look down the list: each document shows which schedules will read it. One marked “No schedule reads it” needs a look.'],
        ['Do this again whenever you add or remove files.'],
      ],
      where: 'Left panel › Documents',
      go: ['Open Documents', '#documents'] },
    { id: 'read', icon: 'doc', title: 'Read each schedule',
      lead: 'A schedule is one part of the return: Salary, Capital gains, Other sources and so on. Reading fills in its figures from your documents.',
      does: [
        ['Open ', ui('Schedules'), ' in the left panel. Each card says what the schedule is and has its own ',
         ui('Read documents'), ' button; ', ui('Read the waiting'), ' at the top does them one after another.'],
        ['Each takes a minute or two, and several can run at once. Start with ', ui('General information'), ', then work down the list.'],
        ['The tax is worked out again by itself after every reading. Nothing else needs pressing.'],
      ],
      where: 'Left panel › Schedules',
      go: ['Open Schedules', '#schedules'] },
    { id: 'check', icon: 'overview', title: 'Look at the result',
      lead: 'The Summary shows the tax payable or refund, your tax rates, where the income came from and how much is already paid.',
      does: [
        ['Open ', ui('Summary'), ' and see whether the picture looks right to you.'],
        ['Click any figure, anywhere, to see how it was reached and the line in your document it came from.'],
        ['If a figure is wrong, correct it right there with a reason. Your correction is kept even when the schedule is read again.'],
      ],
      where: 'Left panel › Summary',
      go: ['Open Summary', '#overview'] },
    { id: 'review', icon: 'review', title: 'Review: settle what only you can decide',
      lead: 'Each reading raises things the documents cannot answer: a question, a credit of unknown nature, a difference nothing explains.',
      does: [
        ['Open ', ui('Review'), '. Differences come first, then questions schedule by schedule.'],
        ['Open each item, choose what to do with it and write the reason. The reason is your record if anyone asks later.'],
        ['Work through them until the count beside Review in the left panel is gone.'],
      ],
      where: 'Left panel › Review',
      go: ['Open Review', '#review'] },
    { id: 'reconcile', icon: 'reconcile', title: 'Reconcile with the department’s record',
      lead: 'The AIS, TIS and Form 26AS are what employers, banks and brokers told the department about you. Your return should agree with them, or you should know why not.',
      does: [
        ['Open ', ui('Reconcile'), ' and press ', ui('Reconcile'), ' on each schedule that has been read.'],
        ['Every line comes back as agrees, accounted for, or needs you. Only “needs you” asks for action; those also appear in Review.'],
        ['If you added last year’s filed return, it is set beside this computation line by line as well.'],
      ],
      where: 'Left panel › Reconcile',
      go: ['Open Reconcile', '#reconcile'] },
    { id: 'handoff', icon: 'handoff', title: 'Hand-off: enter the figures and file',
      lead: 'Flow files nothing. It gives you every schedule in the form’s own line numbers, ready to type into the e-filing utility.',
      does: [
        ['Open ', ui('Hand-off'), '. Pick a schedule on the left, type its lines into the utility and tick each one as you go.'],
        ['Press ', ui('Export to Excel'), ' to get the whole return as ', ui('results.xlsx'), ' in the results folder, to keep or send to your accountant.'],
        ['Before you submit in the utility, compare its final tax with Flow’s. Interest under sections 234A, 234B and 234C is added by the utility, not by Flow.'],
      ],
      extra: () => el('div', { class: 'where' }, pathRow('Results', p.data_path)),
      where: 'Left panel › Hand-off',
      go: ['Open Hand-off', '#handoff'] },
  ];
  return steps;
}

const GUIDE_TIPS = [
  ['bolt', 'Reading and computing are different', 'The AI engine reads: it copies facts out of your documents. Flow computes: it applies the tax rules, instantly and by itself. You only ever ask for a reading.'],
  ['refresh', 'Added or changed a document?', 'Sort the documents again (step 3), then read the schedules it belongs to again (step 4). Everything after that updates.'],
  ['pencil', 'Your work is never overwritten', 'Reading a schedule again keeps every correction and every decision you made.'],
  ['info', 'Stuck on a figure?', 'Click it. The panel that opens shows the working, the printed line in your document and what the department holds.'],
  ['warn', 'A draft, not a filing', 'Flow submits nothing. You file in the e-filing utility, and for anything but a simple return a professional should check it.'],
  ['user', 'More than one return', 'Add a return for another person or year under Returns, and switch with Return at the top.'],
];

/** The page Flow opens on: what it is, the return in hand, how it works, and
 *  how to get started. */
function pageHome() {
  const p = state.activeProfile || {};
  const summary = state.tabs.find((t) => t.id === 'summary')?.document;
  const totals = computedRegime()?.cascade?.totals;
  const engines = (state.engines || []).filter((e) => e.selectable);
  const found = engines.filter((e) => e.available);
  const steps = guideSteps();
  const docs = allDocuments().length;
  const withDocs = state.tabs.filter((t) => t.implemented && t.kind === 'extract' && t.id !== 'filed_return' && t.source_count);
  const read = withDocs.filter((t) => t.document).length;
  const open = openDecisions().length;
  const regime = { new: 'New regime', old: 'Old regime', compare: 'Comparing both regimes' }[p.settings?.regime] || '';
  const refund = totals && totals.refund > 0;

  // ---- the opening: what this is, in one breath
  const point = (iconName, text) => el('li', {}, icon(iconName), text);
  const intro = el('div', { class: 'home-intro' },
    el('div', { class: 'home-eyebrow' }, 'Flow · ITR-3 assistant for residents of India'),
    el('h1', {}, 'Your income-tax return, prepared from your own documents'),
    el('p', { class: 'home-lede' },
      'Flow reads your Form 16, AIS, broker and bank statements, works out every schedule of '
      + 'ITR-3, checks the result against what the department holds, and gives you the figures to '
      + 'enter. It runs on your computer and files nothing.'),
    el('div', { class: 'home-cta' },
      totals
        ? el('a', { class: 'primary', href: '#overview' }, 'Open the summary', icon('chev'))
        : el('a', { class: 'primary', href: '#home/start' }, 'Get started', icon('chev')),
      el('a', { class: 'ghost', href: totals ? '#home/start' : '#_profiles' },
        totals ? 'How it works, step by step' : 'Set up your return')),
    el('ul', { class: 'home-points' },
      point('documents', 'Runs on this computer'),
      point('doc', 'Every figure traced to its document'),
      point('reconcile', 'Checked against AIS, TIS and Form 26AS')));

  // ---- the return in hand
  const stat = (n, label, href) => el('a', { class: 'home-stat', href }, el('b', {}, n), el('span', {}, label));
  const current = el('aside', { class: 'home-return' },
    el('div', { class: 'home-return-h' },
      el('span', {}, 'Return'),
      el('a', { class: 'linkish', href: '#_profiles' }, 'Switch or add')),
    el('div', { class: 'home-return-name' }, p.name || '—'),
    el('div', { class: 'home-return-meta' },
      [`FY ${state.fy}`, `AY ${state.ay}`, regime].filter(Boolean).join(' · ')),
    el('div', { class: 'home-balance' + (refund ? ' refund' : '') },
      el('span', {}, totals ? (refund ? 'Refund due' : 'Balance payable') : 'Tax position'),
      totals ? el('b', {}, inr(refund ? totals.refund : totals.payable))
             : el('b', { class: 'none' }, 'Not computed yet')),
    summary?.computed_at ? el('div', { class: 'home-when' }, `Computed ${fmtWhen(summary.computed_at)}`) : null,
    el('div', { class: 'home-stats' },
      stat(String(docs), docs === 1 ? 'document' : 'documents', '#documents'),
      stat(`${read}/${withDocs.length}`, 'schedules read', '#schedules'),
      stat(String(open), open === 1 ? 'decision open' : 'decisions open', '#review')));

  const hero = el('section', { class: 'home-hero' }, intro, current);

  // ---- how it works, as a picture
  const box = (n, iconName, title, text, cls = '') => el('div', { class: `home-flow-box ${cls}` },
    el('span', { class: 'home-flow-n' }, n), icon(iconName), el('b', {}, title), el('p', {}, text));
  const arrow = () => el('div', { class: 'home-flow-arrow', 'aria-hidden': 'true' }, icon('chev'));
  const how = el('section', { class: 'home-section' },
    el('h2', {}, 'How Flow works'),
    el('div', { class: 'home-flow' },
      box('1', 'documents', 'You add documents', 'Everything for the year in one folder. No sorting or renaming.'),
      arrow(),
      box('2', 'doc', 'The AI engine reads', 'Claude Code or Codex copies the facts out of each document.', 'ai'),
      arrow(),
      box('3', 'calc', 'Flow computes and checks', 'The tax rules, applied by Flow itself, then reconciled with the AIS, TIS and 26AS.'),
      arrow(),
      box('4', 'handoff', 'You file', 'The figures in the form’s own line numbers, to enter in the e-filing utility.')));

  // ---- getting started, as a section of this page
  const stepCard = (s, i) => el('article', { class: 'home-step', id: `step-${s.id}` },
    el('div', { class: 'home-step-h' },
      el('span', { class: 'home-step-n' }, String(i + 1)),
      icon(s.icon)),
    el('h3', {}, s.title),
    el('p', {}, s.lead),
    el('details', { class: 'home-step-how' },
      el('summary', {}, 'How to do it'),
      el('ul', {}, s.does.map((d) => el('li', {}, ...d))),
      s.extra ? s.extra() : null,
      el('div', { class: 'home-step-where' }, icon('open'), s.where)),
    s.go ? el('a', { class: 'home-step-go', href: s.go[1] }, s.go[0], icon('chev')) : null);

  const engine = el('div', { class: 'home-engine' + (found.length ? '' : ' warn') },
    icon(found.length ? 'check' : 'warn'),
    el('div', {},
      el('b', {}, found.length ? 'Reading engine ready' : 'Before you begin: install a reading engine'),
      el('span', {}, found.length
        ? ` ${found.map((e) => e.label).join(' and ')} found on this computer.`
        : ' Flow reads documents with the Claude Code or Codex command-line tool, installed and signed in. '
          + 'The desktop app or the website is not enough. Install one, sign in, and start Flow again.')));

  const start = el('section', { class: 'home-section', id: 'getting-started' },
    el('div', { class: 'home-section-h' },
      el('h2', {}, 'Getting started'),
      el('p', {}, 'Eight steps from a folder of papers to a return ready to file. Follow them in order the '
                  + 'first time; after that, go wherever you need. Open “How to do it” on any step for the detail.')),
    engine,
    el('div', { class: 'home-steps' }, steps.map(stepCard)));

  const tips = el('section', { class: 'home-section' },
    el('h2', {}, 'Good to know'),
    el('div', { class: 'tips' }, GUIDE_TIPS.map(([i, t, x]) =>
      el('div', { class: 'tip' }, icon(i), el('div', {}, el('b', {}, t), el('p', {}, x))))));

  const foot = el('footer', { class: 'home-foot' },
    'A draft for your review, not a filing. Flow sends nothing anywhere; documents are read by the engine you '
    + 'chose, under your own account. ', el('a', { href: '#_profiles' }, 'Where your files are'), '.');

  return [hero, how, start, tips, foot];
}
