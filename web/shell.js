/* Flow: the frame around the schedules.
 *
 * app.js draws each schedule and pages.js draws the places that are not one.
 * This file is what surrounds them: the header that is always in view, the
 * navigation, the routing between places, the page a schedule sits on, the
 * evidence beside a figure, and search.
 *
 * Four things stay in view whatever is open: which return this is, a way to
 * find any line or amount, whether the figures are current, and what is owed.
 */

/* ------------------------------------------------------------------ icons */

const ICONS = {
  home: '<path d="M4 11.2L12 4.5l8 6.7M6.5 9.5v10h4v-5.5h3v5.5h4v-10"/>',
  overview: '<rect x="4" y="4" width="7" height="8" rx="1.5"/><rect x="13" y="4" width="7" height="5" rx="1.5"/><rect x="13" y="11" width="7" height="9" rx="1.5"/><rect x="4" y="14" width="7" height="6" rx="1.5"/>',
  documents: '<path d="M3.5 7a2 2 0 0 1 2-2h3.6l2 2.2h7.4a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
  review: '<path d="M4.5 6.6l1.6 1.6L9 5.3M4.5 12.6l1.6 1.6L9 11.3M4.5 18.2h4M12.5 6.8h7M12.5 12.8h7M12.5 18.2h7"/>',
  reconcile: '<path d="M7 4v13M4 14l3 3 3-3M17 20V7M14 10l3-3 3 3"/>',
  handoff: '<path d="M9 4.5h6v3H9zM9 6H6.5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H15M9 13.5l2 2 4-4.5"/>',
  planning: '<path d="M4 19.5h16M5.5 15.5l4-4.5 3.5 3 5.5-6.5M15 7.5h3.5V11"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  doc: '<path d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5H7a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5zM14 3.5v4h4"/>',
  calc: '<rect x="6" y="3.5" width="12" height="17" rx="2"/><path d="M9 7.5h6M9 11.5h.01M12 11.5h.01M15 11.5h.01M9 14.5h.01M12 14.5h.01M15 14.5h.01M9 17.5h.01M12 17.5h.01M15 17.5h.01"/>',
  pencil: '<path d="M4.5 19.5l1-4L16 5l3 3L8.5 18.5zM14 7l3 3"/>',
  copy: '<rect x="9" y="9" width="10.5" height="11" rx="2"/><path d="M5.5 15V6a2 2 0 0 1 2-2H15"/>',
  open: '<path d="M13.5 5H19v5.5M19 5l-8 8M10.5 6.5H6a1 1 0 0 0-1 1V18a1 1 0 0 0 1 1h10.5a1 1 0 0 0 1-1v-4.5"/>',
  refresh: '<path d="M19 12a7 7 0 1 1-2-4.9M19 4.5v4h-4"/>',
  download: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>',
  warn: '<path d="M12 4.5l8.5 14.5h-17zM12 10v4M12 16.7v.1"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 7.8v.1"/>',
  help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 1 1 3.6 2.3c-.8.4-1.2 1-1.2 1.9M12 16.8v.1"/>',
  bolt: '<path d="M13 3.5L5.5 13.5H11l-1 7 8.5-10.5H13z"/>',
  user: '<circle cx="12" cy="8.2" r="3.5"/><path d="M5 19.5c.6-3.6 3.5-5.6 7-5.6s6.4 2 7 5.6"/>',
  sort: '<path d="M4 6.5h16M7 12h10M10 17.5h4"/>',
};

/** One of the line icons above. The markup is fixed text from this file, never
 *  anything read from a document. */
function icon(name, cls = 'ico') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  if (cls) svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = ICONS[name] || '';
  return svg;
}

/* --------------------------------------------------------- places and names */

const AREAS = [
  { id: 'documents', label: 'Documents', icon: 'documents' },
  { id: 'schedules', label: 'Schedules', icon: 'calc' },
  { id: 'overview', label: 'Summary', icon: 'overview' },
  { id: 'review', label: 'Review', icon: 'review' },
  { id: 'reconcile', label: 'Reconcile', icon: 'reconcile' },
  { id: 'handoff', label: 'Hand-off', icon: 'handoff' },
  { id: 'planning', label: 'Planning', icon: 'planning' },
];

// The schedules, grouped the way a return is thought about and not in the
// order the tabs were numbered. A schedule that exists only to feed another
// sits under it.
const SCHEDULE_GROUPS = [
  { label: 'Income', items: [['salary'], ['house_property'],
                             ['business_computation', ['books', 'depreciation']],
                             ['capital_gains', ['scrip_112a']], ['vda'], ['other_sources']] },
  { label: 'Deductions and losses', items: [['deductions'], ['setoff_cfl']] },
  { label: 'Tax', items: [['summary'], ['taxes_paid']] },
  { label: 'Disclosures', items: [['foreign_special'], ['assets_liabilities'], ['general']] },
];

const NAMES = {
  general: 'General information', salary: 'Salary', house_property: 'House property',
  books: 'Books', business_computation: 'Business', depreciation: 'Depreciation',
  capital_gains: 'Capital gains', scrip_112a: 'Schedule 112A',
  vda: 'Virtual digital assets', other_sources: 'Other sources', deductions: 'Deductions',
  taxes_paid: 'Taxes paid', setoff_cfl: 'Set-off and carry forward',
  foreign_special: 'Foreign income', assets_liabilities: 'Assets and liabilities',
  summary: 'Computation', filed_return: 'Filed return',
};

const ROUTES = { home: 'Home', engines: 'Reading engines', about: 'Help and about', overview: 'Summary', documents: 'Documents', schedules: 'Schedules', review: 'Review',
                 reconcile: 'Reconcile', handoff: 'Hand-off', planning: 'Planning', help: 'Getting started',
                 _profiles: 'Returns' };

const tabOf = (id) => state.tabs.find((t) => t.id === id) || null;
const tabName = (id) => NAMES[id] || tabOf(id)?.title || ROUTES[id] || id;

function navGroupOf(id) {
  for (const group of SCHEDULE_GROUPS) {
    for (const [parent, kids] of group.items) {
      if (parent === id) return { group: group.label, parent: null };
      if ((kids || []).includes(id)) return { group: group.label, parent };
    }
  }
  return { group: id === 'filed_return' ? 'Reconcile' : 'Schedules', parent: null };
}

/* -------------------------------------------------------- computed figures */

const summaryDoc = () => tabOf('summary')?.document || null;

/** The rows of Part B-TI or Part B-TTI, as the computation printed them. */
function partRows(code) {
  const rows = [];
  for (const stage of computedRegime()?.cascade?.stages || []) {
    if (stage.code === code && stage.table?.columns?.[0] === 'Line') rows.push(...stage.table.rows);
  }
  return rows;
}

function partLine(code, item) {
  const row = partRows(code).find((r) => String(r[0]) === String(item));
  return row && typeof row[2] === 'number' ? row[2] : null;
}

function partLabel(code, item) {
  const row = partRows(code).find((r) => String(r[0]) === String(item));
  return row ? String(row[1]) : '';
}

/** What is owed or due back, from the same totals Part B-TTI is drawn from. */
function balance() {
  const totals = computedRegime()?.cascade?.totals;
  if (!totals) return null;
  return totals.refund > 0 ? { kind: 'refund', amount: totals.refund, position: -totals.refund }
                           : { kind: 'payable', amount: totals.payable, position: totals.payable };
}

// The one line of the return each schedule ends up on. It is what the
// navigation shows beside a schedule, and what "where this is used" points at.
const HEADLINE = {
  salary: ['Part B-TI', '1'], house_property: ['Part B-TI', '2'],
  business_computation: ['Part B-TI', '3v'], capital_gains: ['Part B-TI', '4e'],
  vda: ['Part B-TI', '4d'], other_sources: ['Part B-TI', '5d'],
  deductions: ['Part B-TI', '12c'], taxes_paid: ['Part B-TTI', '10e'],
  foreign_special: ['Part B-TTI', '6d'], summary: ['Part B-TTI', '7'],
};

function headline(tabId) {
  const tab = tabOf(tabId);
  if (!tab || !computedRegime()) return null;
  if (tabId === 'depreciation') {
    return computedRegime()?.business?.depreciation_schedule?.total_depreciation ?? null;
  }
  if (!HEADLINE[tabId] || (!tab.document && tab.kind !== 'derive')) return null;
  const value = partLine(...HEADLINE[tabId]);
  return value === null ? null : Math.abs(value);
}

/** The filed return's lines that differ, counted once: the taxes-paid lines
 *  are inside Part B-TTI and are shown again under their own heading. */
function filedDiffers(cmp) {
  if (!cmp) return 0;
  return ['Part B-TI', 'Part B-TTI'].reduce((n, p) => n + (cmp.parts?.[p]?.counts?.differs || 0), 0);
}

/* ------------------------------------------------------------- state marks */

function scheduleState(tab) {
  if (isRunning(tab.id)) return { g: 'run', text: 'Being read now' };
  if (runOf(tab.id).lastRun?.status === 'failed') return { g: 'fail', text: 'The last reading failed' };
  if (runOf(tab.id).lastRun?.status === 'stopped' && !tab.document) return { g: 'wait', text: 'Stopped before it finished' };
  if (!tab.implemented) return { g: 'empty', text: 'Not built yet' };
  const open = openDecisions(tab.id).length;
  if (tab.kind === 'derive') {
    if (!tab.document) return { g: 'empty', text: 'Not computed yet' };
    return open ? { g: 'open', text: `${plural(open, 'open decision')}` } : { g: 'ok', text: 'Computed' };
  }
  if (!tab.document) {
    return tab.source_count
      ? { g: 'wait', text: `${plural(tab.source_count, 'document')} waiting to be read` }
      : { g: 'empty', text: 'Nothing supplied' };
  }
  return open ? { g: 'open', text: plural(open, 'open decision') }
              : { g: 'ok', text: 'Read, nothing open' };
}

/** State as a shape as well as a colour, with the words for a screen reader. */
function glyph(g, text) {
  return el('span', { class: 'g ' + g, title: text || null },
    g === 'ok' ? icon('check', '') : g === 'fail' ? '!' : null,
    text ? el('span', { class: 'sr' }, text) : null);
}

/* -------------------------------------------------------------- navigation */

function renderRail() {
  const rail = $('#rail');
  if (!rail) return;
  const here = state.current;
  const nodes = [];

  const counts = {
    documents: documentsNeedingAttention().length,
    schedules: state.tabs.filter((t) => t.implemented && t.kind === 'extract' && t.source_count && !t.document).length,
    review: openDecisions().length,
    reconcile: reconNeeds(),
  };
  const titles = {
    documents: 'documents that need attention', schedules: 'schedules with documents waiting to be read',
    review: 'open decisions',
    reconcile: 'differences that need you',
  };
  nodes.push(el('a', { class: 'nav-item', href: '#home',
                       'aria-current': here === 'home' ? 'page' : null },
    icon('home'), el('span', { class: 'nav-label' }, 'Home')));
  // Where a return starts: who it is for and how it is set up.
  nodes.push(el('a', { class: 'nav-item', href: '#_profiles',
                       'aria-current': here === '_profiles' ? 'page' : null },
    icon('user'), el('span', { class: 'nav-label' }, 'Returns')));
  for (const area of AREAS) {
    const n = counts[area.id] || 0;
    nodes.push(el('a', { class: 'nav-item', href: `#${area.id}`,
                         'aria-current': here === area.id ? 'page' : null },
      icon(area.icon), el('span', { class: 'nav-label' }, area.label),
      n ? el('span', { class: 'nav-count warn', title: `${n} ${titles[area.id]}` }, String(n)) : null));
  }

  const link = (id, child) => {
    const tab = tabOf(id);
    if (!tab) return null;
    const st = scheduleState(tab);
    const amount = headline(id);
    return el('a', { class: 'nav-item' + (child ? ' nav-sub' : ''), href: `#${id}`,
                     title: `${tabName(id)}: ${st.text}`,
                     'aria-current': here === id ? 'page' : null },
      glyph(st.g, st.text), el('span', { class: 'nav-label' }, tabName(id)),
      amount !== null && !child ? el('span', { class: 'nav-amt' }, rupees(amount)) : null);
  };

  // Everything below this line is a schedule of the return.
  nodes.push(el('div', { class: 'nav-sep', role: 'separator' }),
             el('div', { class: 'nav-title' }, 'Schedules of the return'));

  const placed = new Set(['filed_return']);
  for (const group of SCHEDULE_GROUPS) {
    const rows = [];
    for (const [parent, kids] of group.items) {
      placed.add(parent);
      rows.push(link(parent, false));
      for (const kid of kids || []) { placed.add(kid); rows.push(link(kid, true)); }
    }
    if (rows.some(Boolean)) nodes.push(el('div', { class: 'nav-head' }, group.label), ...rows);
  }
  // A schedule added to config/tabs.json later still gets a place.
  // Planning notes are not a schedule of the return; the Planning page reads them.
  const loose = state.tabs.filter((t) => !placed.has(t.id) && t.kind !== 'plan');
  if (loose.length) nodes.push(el('div', { class: 'nav-head' }, 'Other'), ...loose.map((t) => link(t.id, false)));

  nodes.push(el('div', { class: 'nav-spacer' }),
    el('div', { class: 'nav-foot' },
      el('b', {}, 'A draft for review, not a filing'),
      'Nothing here submits anything. ',
      el('a', { href: '#home/start' }, 'Getting started'), ' · ',
      el('a', { href: '#about' }, 'Help')));
  rail.replaceChildren(...nodes.filter(Boolean));
}

/* ------------------------------------------------------------------ header */

function anythingRunning() {
  return state.classifying || state.activity.classifying || state.activity.running.length > 0
    || Object.values(state.runs).some((r) => r.running);
}

/** Whether the computation reflects every schedule as it now stands. */
function freshness() {
  const s = summaryDoc();
  if (anythingRunning()) {
    const local = Object.entries(state.runs).filter(([, r]) => r.running).map(([k]) => k);
    const ids = [...new Set([...state.activity.running, ...local])];
    const names = ids.map((id) => {
      const [tab, kind] = id.split(':');
      return kind ? `comparing ${tabName(tab)}` : `reading ${tabName(tab)}`;
    });
    if (state.classifying || state.activity.classifying) names.unshift('sorting documents');
    return { tone: 'run', text: 'Working', sub: clip(names.join(', '), 44),
             hint: 'Work is running. Figures update when it finishes.' };
  }
  if (!s || !s.regimes || !Object.keys(s.regimes).length) {
    return { tone: 'idle', text: 'Nothing computed yet', hint: 'Press to compute from the schedules read so far.' };
  }
  const computed = Date.parse(s.computed_at);
  const newer = state.tabs.filter((t) => t.kind === 'extract' && t.id !== 'filed_return' && t.document
    && Date.parse(t.document.resolved_at || t.document.generated_at || 0) > computed + 1000);
  if (newer.length) {
    return { tone: 'stale', text: 'Out of date', sub: 'press to recompute',
             hint: `${newer.map((t) => tabName(t.id)).join(', ')} changed after the last computation.` };
  }
  return { tone: 'ok', text: 'Up to date',
           hint: `Computed ${fmtWhen(s.computed_at)}. Every figure reflects the schedules as they now stand. Press to recompute anyway.` };
}

/** The engine the active profile reads with. It is a setting of the profile,
 *  resolved by the server against what is actually installed. */
const engineId = () => state.engine || state.defaultEngine || '';

/** "claude" stands for Claude Code's default model, "claude:opus" for one
 *  model: the same reader, written the full way, so the two compare equal. */
function canonicalEngine(ref) {
  if (!ref || ref.includes(':')) return ref || '';
  const e = (state.engines || []).find((x) => x.id === ref);
  return e && e.default_model ? `${ref}:${e.default_model}` : ref;
}

/** "Claude Code · Opus" for "claude:opus". */
function engineLabel(ref) {
  const full = canonicalEngine(ref);
  const c = (state.engineChoices || []).find((x) => x.value === full);
  return c ? `${c.group} · ${c.label}` : (full || 'none found');
}

function renderHeader() {
  const store = state.profiles || { profiles: [], active: null };
  const sel = $('#profile');
  sel.replaceChildren(...store.profiles.map((p) => el('option', { value: p.id }, p.name)));
  sel.value = store.active || '';



  const f = freshness();
  const fresh = $('#fresh');
  fresh.className = 'fresh ' + f.tone;
  fresh.title = f.hint || '';
  $('#fresh-text').replaceChildren(el('b', {}, f.text), f.sub ? ` · ${f.sub}` : '');

  $('#activity-dot').hidden = !anythingRunning();
  if (!$('#activity-menu').hidden) renderActivity();
}

function renderActivity() {
  const host = $('#activity-menu');
  const blocks = [];
  if (state.classifyLog.length) {
    blocks.push(el('div', { class: 'act' },
      el('div', { class: 'act-t' },
        glyph(routingBusy() ? 'run' : 'ok', ''), 'Sorting documents',
        routingBusy() ? stopButton('_classify', 'sorting') : null,
        el('a', { href: '#documents' }, 'Documents')),
      el('div', { class: 'log' }, logLines(state.classifyLog.slice(-6)))));
  }
  for (const [key, run] of Object.entries(state.runs)) {
    if (!run.log.length && !run.running) continue;
    const [tabId, kind] = key.split(':');
    const what = `${kind ? 'Comparing' : tabOf(tabId)?.kind === 'derive' ? 'Recomputing' : 'Reading'} ${tabName(tabId)}`;
    blocks.push(el('div', { class: 'act' },
      el('div', { class: 'act-t' },
        glyph(run.running ? 'run' : run.lastRun?.status === 'failed' ? 'fail' : 'ok', ''),
        what,
        run.running && tabOf(tabId)?.kind !== 'derive' ? stopButton(key, what.toLowerCase()) : null,
        el('a', { href: `#${tabId}${kind ? '/reconciliation' : ''}` }, 'Open')),
      el('div', { class: 'log' }, logLines(run.log.slice(-5)))));
  }
  const elsewhere = state.activity.running.filter((id) => !state.runs[id]?.running);
  for (const id of elsewhere) {
    const [tabId] = id.split(':');
    blocks.push(el('div', { class: 'act' },
      el('div', { class: 'act-t' }, glyph('run', ''), `${tabName(tabId)} is being worked on`,
         stopButton(id, tabName(tabId)),
         el('a', { href: `#${tabId}` }, 'Open')),
      el('div', { class: 'muted', style: 'font-size:12.5px;margin-top:4px' },
         'Started before this page was opened; it will show here when it finishes.')));
  }
  const anything = state.activity.running.length || state.activity.classifying
    || Object.values(state.runs).some((r) => r.running) || routingBusy();
  host.replaceChildren(
    el('div', { class: 'menu-cap act-cap' }, 'Activity',
      anything ? el('button', { class: 'ghost small stop-btn', type: 'button',
        onclick: (e) => { e.currentTarget.disabled = true; stopWork(null); } }, icon('close'), 'Stop everything') : null),
    ...(blocks.length ? blocks : [el('div', { class: 'menu-empty' },
      'Nothing is running, and nothing has run since this page was opened.')]));
}

/* ------------------------------------------------------- menus and toasts */

function closeMenus(except) {
  document.querySelectorAll('.menu-wrap').forEach((wrap) => {
    const menu = wrap.querySelector('.menu');
    if (menu === except) return;
    menu.hidden = true;
    wrap.querySelector('.icon-btn')?.setAttribute('aria-expanded', 'false');
  });
}

function toggleMenu(button, menu, before) {
  const opening = menu.hidden;
  closeMenus(menu);
  if (opening && before) before();
  menu.hidden = !opening;
  button.setAttribute('aria-expanded', String(opening));
}

function toast(text, tone = '') {
  const node = el('div', { class: 'toast' + (tone ? ' ' + tone : '') }, text);
  $('#toasts').append(node);
  setTimeout(() => node.remove(), tone === 'err' ? 9000 : 5200);
}

/** "Balance payable went from X to Y", after something that can move it. */
function balanceChange(before, after, lead) {
  if (!before || !after) return lead;
  const moved = after.position - before.position;
  if (!moved) return `${lead} The balance is unchanged.`;
  const say = (b) => `${b.kind === 'refund' ? 'a refund of' : 'a balance payable of'} ${inr(b.amount)}`;
  return `${lead} The return went from ${say(before)} to ${say(after)}.`;
}

/* ----------------------------------------------------------------- routing */

function parseHash() {
  let raw = location.hash.slice(1);
  try { raw = decodeURIComponent(raw); } catch { /* a stray percent sign: use it as typed */ }
  const [id, ...rest] = raw.split('/');
  return { id, sub: rest.join('/') || null };
}

const isRoute = (id) => Boolean(ROUTES[id]) || state.tabs.some((t) => t.id === id);

function applyRoute() {
  const { id, sub } = parseHash();
  // Getting started is a section of Home now; an old link still lands on it.
  if (id === 'help') { history.replaceState(null, '', '#home/start'); return applyRoute(); }
  if (id === 'models') { history.replaceState(null, '', '#engines'); return applyRoute(); }
  const next = isRoute(id) ? id : 'home';
  const changed = next !== state.current;
  state.current = next;
  state.sub = sub;
  if (changed) closeEvidence(true);
  closeMenus();
  renderRail();
  renderPanel();
  if (changed) window.scrollTo(0, 0);
  document.title = `${tabName(next)} · Flow`;
  $('#start-btn')?.removeAttribute('aria-current');
  if (next === 'home' && sub === 'start') {
    $('#start-btn')?.setAttribute('aria-current', 'page');
    requestAnimationFrame(() => $('#getting-started')?.scrollIntoView({ block: 'start' }));
  }

  // A schedule with no hand-written layout is drawn from its schema, which
  // may not have arrived yet.
  if (tabOf(next) && state.schemas[next] === undefined) {
    ensureSchema(next).then(() => {
      if (state.current === next && state.schemas[next] && !RENDERERS[next]) renderPanel();
    });
  }
}

/** Go to a place. Everything that navigates goes through the address, so the
 *  back button, a bookmark and a link in a note all work the same way. */
function select(id, sub) {
  const target = `#${id}${sub ? `/${sub}` : ''}`;
  if (location.hash === target) applyRoute();
  else location.hash = target;
}

function drawError(err) {
  console.error(err);
  return card('This page could not be drawn',
    el('div', { class: 'card-body' },
      el('p', { style: 'margin:0 0 8px' },
         'The figures are intact; the page failed while laying them out.'),
      el('pre', { id: 'render-error', class: 'src', style: 'white-space:pre-wrap;margin:0' },
         [`${err.name}: ${err.message}`,
          ...String(err.stack || '').split(/\r?\n/).slice(0, 4)].join(String.fromCharCode(10)))),
    'err');
}

function renderPanel() {
  const panel = $('#panel');
  if (!panel) return;
  const id = state.current;
  if (evidence && !document.body.contains(evidence.anchor)) closeEvidence(true);
  if (id === '_profiles') { renderProfiles(); return; }

  let nodes;
  try {
    if (id === 'home') nodes = pageHome();
    else if (id === 'engines') nodes = pageEngines();
    else if (id === 'about') nodes = pageAbout();
    else if (id === 'overview') nodes = pageOverview();
    else if (id === 'documents') nodes = pageDocuments();
    else if (id === 'schedules') nodes = pageSchedules();
    else if (id === 'review') nodes = pageReview();
    else if (id === 'reconcile') nodes = pageReconcile();
    else if (id === 'handoff') nodes = pageHandoff();
    else if (id === 'planning') nodes = pagePlanning();
    else if (tabOf(id)) nodes = pageSchedule(tabOf(id));
    else nodes = pageHome();
  } catch (err) {
    nodes = [drawError(err)];
  }
  panel.replaceChildren(...nodes.flat().filter(Boolean));
  if (evidence && !document.body.contains(evidence.anchor)) closeEvidence(true);
}

/* --------------------------------------------------------- a schedule's page */

function scheduleDocOf(tab) {
  // Set-off and carry forward is computed whether or not an earlier year's
  // losses were supplied -- with none, every line is nil and says so. It must
  // not sit behind "nothing read" just because there was nothing to read.
  return tab.document || (tab.id === 'setoff_cfl' && tab.implemented
    ? { data: { brought_forward: [] }, questions: [], unmapped: [], nothing_supplied: true }
    : null);
}

/** The schedule's own cards, and the ledger behind them kept apart: the form
 *  is what gets entered, the ledger is the evidence for it. */
function scheduleCards(tab, d) {
  let cards;
  try {
    const renderer = RENDERERS[tab.id];
    cards = (renderer ? renderer(d) : renderFromSchema(d, state.schemas[tab.id])) || [];
  } catch (err) {
    cards = [drawError(err)];
  }
  cards = cards.filter(Boolean);
  const isLedger = (node) =>
    /^Ledger\b/.test(node.querySelector?.(':scope > h2')?.firstChild?.textContent || '');
  return { main: cards.filter((n) => !isLedger(n)), ledger: cards.filter(isLedger) };
}

function runAction(tab, d) {
  const derive = tab.kind === 'derive';
  const running = isRunning(tab.id);
  const label = running ? (derive ? 'Recomputing…' : 'Reading…')
    : routingBusy() ? 'Waiting for sorting…'
    : derive ? 'Recompute'
    : d && !d.nothing_supplied ? 'Read again' : 'Read documents';
  const button = el('button', {
    class: d && !d.nothing_supplied && !derive ? 'ghost' : 'primary',
    disabled: running || routingBusy() || (!derive && !tab.source_count),
    title: routingBusy() ? 'Documents are being sorted; reading waits until that finishes.'
      : !derive && !tab.source_count ? 'No document feeds this schedule yet.'
      : derive ? 'Work the computation through again from the schedules as they stand.'
      : 'Read this schedule’s documents with the engine chosen in Settings.',
    onclick: () => runTab(tab),
  }, derive ? null : icon('refresh'), label);
  // While a reading runs, Stop sits beside it.
  return running && !derive ? el('span', { class: 'run-acts' }, button, stopButton(tab.id, `reading ${tabName(tab.id)}`)) : button;
}

function runStripKids(tab) {
  const run = runOf(tab.id);
  const out = [];
  const failed = run.lastRun && run.lastRun.status === 'failed';
  if (run.lastRun?.status === 'stopped') {
    out.push(el('div', { class: 'callout' }, icon('info'),
      el('div', {}, el('b', {}, 'This reading was stopped'),
        run.lastRun.errors || 'Nothing from it was saved.')));
  }
  if (failed) {
    // A failed reading must never be mistaken for a quiet success.
    out.push(el('div', { class: 'callout err' }, icon('warn'),
      el('div', {},
        el('b', {}, 'This reading failed, and nothing was saved'),
        `The ${run.lastRun.engine || 'chosen'} engine could not finish. `
        + (tab.document ? 'What is shown below is from the last reading that succeeded.' : ''),
        el('pre', { class: 'log', style: 'margin:8px 0 0' }, run.lastRun.errors || 'no detail reported'))));
  }
  if (run.log.length) {
    out.push(el('div', { class: 'log', id: `log-${tab.id}` }, logLines(run.log)));
  } else if (state.activity.running.includes(tab.id)) {
    out.push(el('div', { class: 'log' },
      'This schedule is being read now. It was started before this page was opened.'));
  }
  return out;
}

/** Called for every line a run streams. Only the progress strip is redrawn,
 *  so whatever is open on the page stays open. */
function runProgress(key) {
  renderHeader();
  const [tabId] = key.split(':');
  const box = document.getElementById(`log-${key}`);
  const run = runOf(key);
  if (box) {
    box.replaceChildren(...logLines(run.log));
    box.scrollTop = box.scrollHeight;
    return;
  }
  if (state.current === tabId || state.current === 'reconcile') renderPanel();
}

function historyCards(tab, d) {
  const out = [];
  const overrides = d?.overrides_applied || [];
  const live = overrides.filter((o) => o.state !== 'stale');
  if (overrides.length) {
    out.push(card(`Your corrections (${live.length} active of ${overrides.length})`,
      table(['Figure', { t: 'As read', num: true }, { t: 'Corrected to', num: true }, 'Why'],
        overrides.map((o) => el('tr', {},
          el('td', {}, el('span', { class: 'src', style: 'overflow-wrap:anywhere' }, o.pointer),
             chip(o.state === 'applied' ? 'In effect' : o.state === 'stale' ? 'The document now agrees'
                  : o.state === 'manual' ? 'Entered by you' : 'No longer applies',
                  o.state === 'applied' || o.state === 'manual' ? 'warn' : '')),
          el('td', { class: 'num' }, typeof o.was === 'number' ? rupees(o.was) : '—'),
          el('td', { class: 'num' }, typeof o.value === 'number' ? rupees(o.value) : String(o.value)),
          el('td', {}, o.reason, o.at ? el('span', { class: 'why' }, fmtWhen(o.at)) : null)))),
      '', el('span', { class: 'src' }, 'kept apart from the readings, and applied again after each one')));
  }

  const settled = Object.values(state.decisions?.current || {}).filter((e) => e.tab === tab.id);
  if (settled.length) {
    out.push(card(`Decisions settled (${settled.length})`,
      table(['What was decided', 'Why', 'When'], settled.map((e) => el('tr', {},
        el('td', {}, el('b', {}, e.choice_label), el('span', { class: 'why' }, clip(e.text, 220))),
        el('td', {}, e.reason),
        el('td', { class: 'nowrap muted' }, fmtWhen(e.at)))))));
  }

  if (d && (d.run_id || d.generated_at || d.computed_at)) {
    const facts = [
      ['Reading', d.run_id], ['Engine', d.engine?.model], ['Instructions', d.engine?.prompt_version],
      ['Read', d.generated_at ? fmtWhen(d.generated_at) : null],
      ['Computed', d.computed_at ? fmtWhen(d.computed_at) : null],
      ['Corrections last applied', d.resolved_at ? fmtWhen(d.resolved_at) : null],
      ['Fingerprint of what was read', d.input_fingerprint],
    ].filter(([, v]) => v);
    out.push(card(tab.kind === 'derive' ? 'The last computation' : 'The last reading',
      table(null, facts.map(([k, v]) => el('tr', {},
        el('td', {}, k), el('td', { class: 'src', style: 'text-align:right;overflow-wrap:anywhere' }, String(v))))),
      '', el('span', { class: 'src' },
        'the same documents, instructions and engine give the same fingerprint')));
  }
  if (!out.length) {
    out.push(el('section', { class: 'card' }, el('div', { class: 'empty-state' },
      el('h3', {}, 'Nothing has happened here yet'),
      el('p', {}, 'Readings, corrections and decisions for this schedule are listed here as they are made.'))));
  }
  return out;
}

function documentCards(tab, d) {
  const out = [];
  if (tab.id === 'summary') {
    const from = (summaryDoc()?.contributors || []);
    out.push(card(`Built from ${from.length} schedule(s)`,
      from.length ? table(['Schedule', { t: 'Documents', num: true }, 'Read', ''],
        from.map((c) => el('tr', {},
          el('td', {}, tabName(c.tab), el('span', { class: 'src' }, c.run_id || '')),
          el('td', { class: 'num' }, String((c.sources || []).length)),
          el('td', { class: 'muted' }, c.generated_at ? fmtWhen(c.generated_at) : '—'),
          el('td', {}, el('a', { class: 'linkish', href: `#${c.tab}` }, 'Open')))))
        : el('div', { class: 'card-body empty' }, 'No schedule has been read yet.'),
      '', el('span', { class: 'src' }, 'the computation reads no documents of its own')));
    return out;
  }
  if (tab.kind === 'derive') {
    out.push(derivedFromCard(tab, d));
    const upstream = inheritedDocuments(tab, d);
    out.push(documentsCard({ ...tab, documents: upstream.documents,
                             resolved_sources: upstream.sources }, upstream.merged));
    return out;
  }
  out.push(documentsCard(tab, d));
  if ((tab.archives || []).length) {
    out.push(card(`${tab.archives.length} archive(s) nothing can read inside`,
      el('div', { class: 'card-body' },
        el('ul', { class: 'plain' }, tab.archives.map((a) => el('li', {}, a)))), 'warn'));
  }
  if (d?.sources?.length) {
    out.push(card('What the last reading was given',
      table(['File', { t: 'Bytes', num: true }, 'SHA-256'],
        d.sources.map((s) => el('tr', {},
          el('td', { class: 'desc' }, s.path),
          el('td', { class: 'num' }, s.bytes?.toLocaleString('en-IN')),
          el('td', { class: 'src' }, `${String(s.sha256 || '').slice(0, 16)}…`)))),
      '', el('span', { class: 'src' }, 'the hash identifies the exact file that was read')));
  }
  return out;
}

function pageSchedule(tab) {
  const d = scheduleDocOf(tab);
  const st = scheduleState(tab);
  const where = navGroupOf(tab.id);
  const isFiled = tab.id === 'filed_return';
  const cards = d && tab.implemented ? scheduleCards(tab, d) : { main: [], ledger: [] };
  const items = reviewItems().filter((i) => i.tab === tab.id);
  const open = items.filter((i) => i.counts && !i.settled).length;
  const canReconcile = tab.reconcilable && tab.kind === 'extract' && !isFiled;
  const needs = canReconcile && tab.reconciliation ? reconCounts(tab).needs : 0;
  const docCount = tab.kind === 'derive' ? null : (tab.documents || []).length;

  // A filed return, where one has been supplied, is set beside the computation
  // on the computation's own page as well as under Reconcile: this is where
  // the two are read side by side, line for line.
  const filedCmp = tab.id === 'summary' ? computedRegime()?.filed_comparison || null : null;
  const filedDiffer = filedDiffers(filedCmp);

  const tabs = [{ id: 'schedule', label: tab.id === 'summary' ? 'Computation' : 'Schedule' }];
  if (filedCmp) tabs.push({ id: 'filed', label: 'Against the filed return', count: filedDiffer || null, warn: true });
  if (cards.ledger.length) tabs.push({ id: 'ledger', label: 'Ledger' });
  if (canReconcile) tabs.push({ id: 'reconciliation', label: 'Reconciliation', count: needs || null, warn: true });
  tabs.push({ id: 'documents', label: tab.kind === 'derive' ? 'Built from' : 'Documents', count: docCount });
  if (tab.id !== 'summary') tabs.push({ id: 'decisions', label: 'Decisions', count: open || null, warn: true });
  tabs.push({ id: 'history', label: 'History' });
  const active = tabs.some((t) => t.id === state.sub) ? state.sub : 'schedule';

  const crumbs = el('nav', { class: 'crumbs', 'aria-label': 'Where you are' },
    isFiled ? el('a', { href: '#reconcile/filed' }, 'Reconcile') : el('span', {}, 'Schedules'),
    isFiled ? null : el('span', { class: 'sep' }, '/'),
    isFiled ? null : el('span', {}, where.group),
    where.parent ? el('span', { class: 'sep' }, '/') : null,
    where.parent ? el('a', { href: `#${where.parent}` }, tabName(where.parent)) : null,
    el('span', { class: 'sep' }, '/'), el('span', {}, tabName(tab.id)));

  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('div', { class: 'page-title' },
        el('h1', {}, tabName(tab.id)),
        ...(tab.schedules || []).map((s) => el('span', { class: 'chip mono' }, s)),
        chip(st.text, st.g === 'ok' ? 'ok' : st.g === 'open' || st.g === 'wait' ? 'warn'
                      : st.g === 'fail' ? 'err' : st.g === 'run' ? 'info' : 'line')),
      tab.conditional ? el('p', { class: 'page-sub' }, tab.conditional) : null),
    el('div', { class: 'page-actions' }, tab.implemented ? runAction(tab, d) : null));

  const meta = el('div', { class: 'meta-row' },
    d?.generated_at && tab.kind !== 'derive' ? el('span', {}, `Read ${fmtWhen(d.generated_at)}`) : null,
    d?.generated_at && tab.kind === 'derive' ? el('span', {}, `Computed ${fmtWhen(d.generated_at)}`) : null,
    d?.computed_at ? el('span', {}, `Computed ${fmtWhen(d.computed_at)}`) : null,
    !d && tab.kind !== 'derive' ? el('span', {}, tab.source_count
      ? `${plural(tab.source_count, 'document')} waiting to be read` : 'No document feeds this schedule') : null,
    d?.sources?.length ? el('span', { class: 'dotsep' }, `from ${plural(d.sources.length, 'document')}`) : null,
    d?.engine?.model ? el('span', { class: 'dotsep mono' },
      [d.engine.model, d.engine.prompt_version].filter(Boolean).join(' · ')) : null,
    isFiled ? el('span', { class: 'dotsep' }, 'used only for comparison; it feeds no figure') : null);
  // Never a schedule without saying how it reconciles.
  const reconLine = canReconcile && (d || tab.reconciliation) ? el('div', { class: 'meta-row recon-line' },
    el('a', { href: `#${tab.id}/reconciliation` }, 'Department’s record'),
    ...reconChips(tab)) : null;
  const filedAgree = filedCmp ? ['Part B-TI', 'Part B-TTI']
    .reduce((n, p) => n + (filedCmp.parts?.[p]?.counts?.agrees || 0), 0) : 0;
  const filedLine = filedCmp ? el('div', { class: 'meta-row recon-line' },
    el('a', { href: '#summary/filed' }, 'Filed return'),
    filedDiffer ? chip(`${filedDiffer} ${filedDiffer === 1 ? 'line differs' : 'lines differ'}`, 'warn')
                : chip('Agrees on every line', 'ok'),
    filedAgree ? chip(`${filedAgree} agree`, 'ok') : null,
    el('a', { class: 'linkish', href: '#summary/filed' }, 'Compare side by side')) : null;

  const tabBar = el('div', { class: 'tabs', role: 'tablist' }, tabs.map((t) =>
    el('a', { class: 'tab', role: 'tab', href: `#${tab.id}${t.id === 'schedule' ? '' : `/${t.id}`}`,
              'aria-selected': String(t.id === active) },
      t.label,
      t.count ? el('span', { class: 'tab-count' + (t.warn ? ' warn' : '') }, String(t.count)) : null)));

  let body;
  if (!tab.implemented) {
    body = [el('section', { class: 'card' }, el('div', { class: 'empty-state' },
      el('h3', {}, 'Not built yet'),
      el('p', {}, 'This schedule is listed so the whole shape of the ITR-3 stays in view, but '
        + 'nothing reads or computes it yet. It is not being treated as nil: the Computation page '
        + 'lists it as left out.')))];
  } else if (active === 'filed' && filedCmp) {
    body = filedView();
  } else if (active === 'ledger') {
    body = cards.ledger;
  } else if (active === 'reconciliation') {
    body = [reconWorkspace([tab])];
  } else if (active === 'documents') {
    body = documentCards(tab, d);
  } else if (active === 'decisions') {
    body = scheduleDecisions(tab);
  } else if (active === 'history') {
    body = historyCards(tab, d);
  } else if (!d) {
    body = [el('section', { class: 'card' }, el('div', { class: 'empty-state' },
      el('h3', {}, tab.kind === 'derive' ? 'Not computed yet'
        : tab.source_count ? 'Nothing has been read for this schedule yet' : 'No document feeds this schedule'),
      el('p', {}, tab.kind === 'derive'
        ? 'Press Recompute once the schedules this is built from have been read.'
        : tab.source_count
          ? `${plural(tab.source_count, 'document is', 'documents are')} waiting. Reading fills this `
            + 'schedule’s lines and the computation follows on its own.'
          : 'If this schedule applies to you, add its documents to the folder and sort them again '
            + 'on the Documents page. If it does not, there is nothing to do: it stays nil.'),
      tab.source_count || tab.kind === 'derive' ? runAction(tab, d)
        : el('a', { class: 'ghost', href: '#documents' }, 'Go to Documents')))];
  } else {
    body = cards.main;
  }

  return [crumbs, head, meta, reconLine, filedLine,
    el('div', { id: 'run-strip' }, ...runStripKids(tab)),
    tabBar,
    el('div', { class: 'tab-body', role: 'tabpanel' }, ...body)];
}

/* ---------------------------------------------------------------- evidence */

let evidence = null;
const excerpts = new Map();

/** The printed line behind a figure, fetched from the text the engine read. */
function excerptBlock(cite, amount, source) {
  const host = el('div', {}, el('div', { class: 'skeleton' }));
  const key = `${cite}|${amount}|${source || ''}`;

  const draw = (r) => {
    if (!r.found) {
      host.replaceChildren(el('p', { class: 'muted' }, r.why || 'The line could not be found.'));
      return;
    }
    const blocks = r.matches.map((m) => el('div', { class: 'excerpt' },
      el('div', { class: 'excerpt-h' },
        [m.file, m.page ? `page ${m.page}` : null, `line ${m.line}`].filter(Boolean).join(' · ')),
      el('pre', {},
        m.before.length ? m.before.join('\n') + '\n' : '',
        el('span', { class: 'hit' }, m.text.slice(0, m.start),
           el('mark', {}, m.text.slice(m.start, m.end)), m.text.slice(m.end)),
        m.after.length ? '\n' + m.after.join('\n') : '')));
    host.replaceChildren(...blocks);
    if (r.total > r.matches.length) {
      host.append(el('p', { class: 'muted', style: 'font-size:12.5px' },
        `These digits appear ${r.total} times in the document; the first ${r.matches.length} are shown`
        + (r.page ? ', the cited page first.' : '.')));
    }
  };

  if (excerpts.has(key)) {
    draw(excerpts.get(key));
  } else {
    const query = new URLSearchParams({ ay: state.ay || '', cite: cite || '', amount: String(amount ?? ''),
                                        source: source || '' });
    getJSON(`/api/excerpt?${query}`).then((r) => { excerpts.set(key, r); draw(r); })
      .catch((err) => host.replaceChildren(el('p', { class: 'muted' }, `Could not look it up: ${err.message}`)));
  }
  return host;
}

/** Open one of this return's own documents in a new tab. */
async function openDocument(path, page) {
  // Opened before the fetch, while the click still counts as the person's
  // own, or the browser treats it as a pop-up and blocks it.
  const win = window.open('about:blank', '_blank');
  try {
    const res = await api(`/api/file?${new URLSearchParams({ ay: state.ay || '', path })}`);
    const url = URL.createObjectURL(await res.blob());
    if (win) win.location.href = url + (page ? `#page=${page}` : '');
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 300000);
  } catch (err) {
    if (win) win.close();
    toast(`Could not open the document: ${err.message}`, 'err');
  }
}

/** The words on a row that say what the figure is, without the small print. */
function rowLabel(anchor) {
  const tr = anchor?.closest('tr');
  if (!tr) return '';
  const first = tr.querySelector('td, th');
  if (!first || first.contains(anchor)) return '';
  const copy = first.cloneNode(true);
  copy.querySelectorAll('.why, .src, .cite, .caret, .fxwork, .chip').forEach((n) => n.remove());
  const code = copy.querySelector('.item-label');
  const codeText = code ? code.textContent.trim() : '';
  code?.remove();
  const text = copy.textContent.replace(/\s+/g, ' ').trim();
  const cell = anchor.closest('td');
  const index = cell ? [...tr.children].indexOf(cell) : -1;
  const heading = index > 0
    ? tr.closest('table')?.querySelector(`thead th:nth-child(${index + 1})`)?.textContent?.trim() : '';
  return [[codeText, text].filter(Boolean).join(' '),
          heading && !/^amount/i.test(heading) ? heading : null].filter(Boolean).join(' · ');
}

// Part B-TI names the schedule each line is carried from; this is where that
// name leads.
const SCHEDULE_REFS = [
  [/Schedule[- ]?S\b/i, 'salary'], [/Schedule[- ]?HP\b/i, 'house_property'],
  [/Schedule[- ]?BP\b/i, 'business_computation'], [/Schedule[- ]?CG\b/i, 'capital_gains'],
  [/Schedule[- ]?OS\b/i, 'other_sources'], [/Schedule[- ]?VI-?A\b/i, 'deductions'],
  [/Schedule[- ]?(CYLA|BFLA|CFL)\b/i, 'setoff_cfl'], [/Schedule[- ]?TR\b/i, 'foreign_special'],
  [/17[A-D]\b|TDS|TCS|Advance Tax|Self Assessment/i, 'taxes_paid'],
];

function openEvidence(context) {
  const tabId = tabOf(state.current) ? state.current : context.tab || null;
  document.querySelectorAll('.money.selected').forEach((n) => n.classList.remove('selected'));
  context.anchor?.classList.add('selected');
  evidence = { ...context, tab: context.tab || tabId,
               label: context.line ? `${context.line.item} ${context.line.label}` : rowLabel(context.anchor) };
  document.body.classList.add('has-evidence');
  $('#evidence').hidden = false;
  renderEvidence();
  $('#evidence .icon-btn')?.focus({ preventScroll: true });
}

function closeEvidence(quiet) {
  if (!evidence && $('#evidence').hidden) return;
  const anchor = evidence?.anchor;
  evidence = null;
  document.querySelectorAll('.money.selected').forEach((n) => n.classList.remove('selected'));
  document.body.classList.remove('has-evidence');
  $('#evidence').hidden = true;
  if (!quiet && anchor && document.body.contains(anchor)) anchor.focus({ preventScroll: true });
}

function renderEvidence() {
  const e = evidence;
  if (!e) return;
  const tab = tabOf(e.tab);
  const cmp = computedRegime()?.filed_comparison;
  const body = [];

  const mark = e.isOverride ? ['fix', 'pencil', 'Corrected by you']
    : e.computed || !e.cite ? ['calc', 'calc', 'Worked out by this tool']
    : ['doc', 'doc', 'Read from a document'];

  // --- how it was reached
  if (e.computed) {
    const ref = SCHEDULE_REFS.find(([re]) => re.test(e.line?.label || ''));
    body.push(sec('How this figure was reached',
      el('p', {}, `${e.line.part} line ${e.line.item}. It is worked out from the lines the form `
        + 'names in its wording, in the order the Act runs them.'),
      ref && tabOf(ref[1]) ? el('p', {}, 'It is carried from ',
        el('a', { href: `#${ref[1]}` }, tabName(ref[1])), '.') : null));
  } else {
    const o = e.isOverride
      ? (tab?.document?.overrides_applied || []).find((x) => x.pointer === e.pointer && x.state !== 'stale') : null;
    body.push(sec('How this figure was reached',
      e.basis ? el('p', { style: 'color:var(--ink)' }, e.basis) : null,
      e.cite ? el('p', { class: 'mono', style: 'font-size:12px' }, e.cite) : null,
      !e.basis && !e.cite ? el('p', {}, 'The reading gave no citation for this figure. Treat it '
        + 'as unverified until you have found it in the document yourself.') : null,
      o ? el('p', {}, `The document was read as ${typeof o.was === 'number' ? inr(o.was) : 'blank'}. `
        + `You corrected it to ${inr(o.value)}${o.at ? `, ${fmtWhen(o.at)}` : ''}: ${o.reason}`) : null,
      e.foreign ? el('p', {}, 'Stated in a foreign currency. The rupee figure comes from the rate '
        + 'the rule fixes for its date, and is shown where it is computed.') : null));
  }

  // --- the printed line
  if (e.cite) {
    const path = String(e.cite).split('#')[0];
    body.push(sec('In the document',
      excerptBlock(e.cite, e.amount),
      el('div', { style: 'margin-top:8px' },
        el('button', { class: 'ghost small', onclick: () => openDocument(path) },
           icon('open'), 'Open the document'))));
  }

  // --- the department's record
  if (tab && tab.reconcilable && tab.kind === 'extract' && tab.id !== 'filed_return') {
    const checks = reconChecks(tab);
    const same = typeof e.amount === 'number'
      ? checks.filter((c) => c.ours === e.amount || c.theirs === e.amount) : [];
    body.push(sec('The department’s record',
      !tab.reconciliation
        ? el('p', {}, 'This schedule has not been compared with the AIS, the TIS and Form 26AS yet.')
        : same.length
          ? el('table', { class: 'sum' }, el('tbody', {}, same.slice(0, 4).map((c) => el('tr', {},
              el('td', {}, c.label, el('span', { class: 'why' },
                 `department ${c.theirs === null ? '—' : inr(c.theirs)}, yours ${c.ours === null ? '—' : inr(c.ours)}`)),
              el('td', { class: 'num' }, chip(RESULT[c.result].label, RESULT[c.result].tone))))))
          : el('p', {}, 'No line of the comparison carries exactly this figure. The schedule as a whole:'),
      tab.reconciliation && !same.length ? el('div', { class: 'chips' }, ...reconChips(tab)) : null,
      el('div', { style: 'margin-top:8px' },
        el('a', { class: 'linkish', href: `#${tab.id}/reconciliation` },
           tab.reconciliation ? 'Open the reconciliation' : 'Compare it now'))));
  }

  // --- the filed return, for a line of Part B
  if (e.line && cmp) {
    const row = (cmp.parts?.[e.line.part]?.rows || []).find((r) => String(r.item) === e.line.item);
    body.push(sec('The filed return',
      row && row.filed !== null
        ? el('dl', { class: 'dl' },
            el('dt', {}, 'Computed here'), el('dd', {}, inr(Math.abs(row.computed))),
            el('dt', {}, 'Filed'), el('dd', {}, inr(Math.abs(row.filed))),
            el('div', { class: row.state === 'differs' ? 'bad' : 'tot', style: 'display:contents' },
              el('dt', {}, row.state === 'differs' ? 'Differs by' : 'Agrees'),
              el('dd', {}, row.state === 'differs' ? inr(row.difference) : '')))
        : el('p', {}, 'The filed return has no line with this number.'),
      el('div', { style: 'margin-top:8px' },
        el('a', { class: 'linkish', href: '#reconcile/filed' }, 'Open the comparison'))));
  }

  // --- where it goes
  if (!e.computed && tab && HEADLINE[tab.id]) {
    const [code, item] = HEADLINE[tab.id];
    const value = partLine(code, item);
    if (value !== null) {
      body.push(sec('Where it is used',
        el('p', {}, `${tabName(tab.id)} is carried to ${code} line ${item}: `,
           el('b', { style: 'color:var(--ink)' }, inr(Math.abs(value))), '.'),
        el('p', { class: 'muted', style: 'font-size:12.5px' }, clip(partLabel(code, item), 150)),
        el('a', { class: 'linkish', href: '#summary' }, 'Open the computation')));
    }
  }

  $('#evidence').replaceChildren(...[
    el('div', { class: 'ev-head' },
      el('h2', {}, 'Evidence'),
      el('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close the evidence panel',
                     onclick: () => closeEvidence() }, icon('close', ''))),
    el('div', { class: 'ev-top' },
      el('div', { class: 'ev-amount' }, e.foreign || inr(e.amount)),
      el('div', { class: 'ev-label' },
        [e.label, tab ? tabName(tab.id) : null].filter(Boolean).join(' · ') || 'Figure'),
      el('span', { class: 'mark ' + mark[0] }, icon(mark[1], ''), mark[2])),
    el('div', { class: 'ev-body' }, ...body),
    e.pointer
      ? el('div', { class: 'ev-foot' },
          el('button', { class: 'ghost', type: 'button',
                         onclick: () => openOverride(e.pointer, e.amount, e.tab) },
             icon('pencil'), 'Correct this value'),
          el('span', { class: 'muted', style: 'font-size:12px;flex:1;min-width:140px' },
             'Kept with its reason, and applied again after every reading.'))
      : null,
  ].filter(Boolean));
}

/* ------------------------------------------------------------------ search */

const palette = { items: [], shown: [], active: 0 };

/** Everything that can be found: places, every line of every schedule, each
 *  document and each open decision. Built when search opens, from what the
 *  page already holds. */
function paletteIndex() {
  const out = [];
  for (const area of AREAS) out.push({ type: 'Go to', label: area.label, hint: 'Area', go: () => select(area.id) });
  out.push({ type: 'Go to', label: 'Getting started', hint: 'Help', go: () => select('home', 'start') });
  out.push({ type: 'Go to', label: 'Help and about', hint: 'User guide', go: () => select('about') });
  out.push({ type: 'Go to', label: 'Reading engines', hint: 'Claude, Codex, Ollama', go: () => select('engines') });
  out.push({ type: 'Go to', label: 'Returns', hint: 'Settings', go: () => select('_profiles') });
  if (computedRegime()?.filed_comparison) {
    out.push({ type: 'Go to', label: 'Computation against the filed return', hint: 'Side by side, line for line',
               go: () => select('summary', 'filed') });
  }
  for (const tab of state.tabs) {
    const amount = headline(tab.id);
    out.push({ type: 'Schedule', label: tabName(tab.id), hint: (tab.schedules || []).join(', '),
               amounts: amount === null ? [] : [amount], go: () => select(tab.id) });
  }
  for (const sheet of state.handoff?.sheets || []) {
    for (const row of sheet.rows) {
      if (row.kind === 'head') continue;
      const amounts = row.values.filter((v) => typeof v === 'number');
      out.push({ type: 'Line', code: row.item, label: row.label, hint: sheet.title.split(':')[0],
                 amounts, go: () => select(sheet.tab) });
    }
  }
  for (const d of allDocuments()) {
    out.push({ type: 'Document', label: d.name, hint: d.kind || d.folder, go: () => select('documents', d.key) });
  }
  for (const item of reviewItems().filter((i) => !i.settled)) {
    out.push({ type: item.counts ? 'Decision' : 'Set aside', label: item.text, hint: tabName(item.tab),
               amounts: typeof item.amount === 'number' && item.amount ? [item.amount] : [],
               go: () => select('review', item.id) });
  }
  return out;
}

function paletteSearch(query) {
  const q = query.trim().toLowerCase();
  if (!q) {
    return palette.items.filter((i) => i.type === 'Go to' || i.type === 'Schedule').slice(0, 24);
  }
  const digits = q.replace(/[,\s₹]/g, '');
  const numeric = /^-?\d+$/.test(digits) && digits.length >= 2;
  const words = q.split(/\s+/).filter(Boolean);
  const scored = [];
  for (const item of palette.items) {
    const text = `${item.code || ''} ${item.label} ${item.hint || ''}`.toLowerCase();
    let score = 0;
    if (numeric) {
      const hit = (item.amounts || []).map((a) => String(Math.abs(a)))
        .find((a) => a === digits.replace('-', '') || a.startsWith(digits.replace('-', '')));
      if (hit) score = hit === digits.replace('-', '') ? 100 : 60;
    }
    if (!score && words.every((w) => text.includes(w))) {
      score = (item.code || '').toLowerCase() === q ? 90
        : item.label.toLowerCase().startsWith(q) ? 50 : 30;
      if (item.type === 'Go to' || item.type === 'Schedule') score += 8;
    }
    if (score) scored.push([score, item]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return scored.slice(0, 40).map(([, item]) => item);
}

function renderPalette() {
  const list = $('#palette-list');
  const query = $('#palette-input').value;
  palette.shown = paletteSearch(query);
  palette.active = Math.min(palette.active, Math.max(0, palette.shown.length - 1));
  if (!palette.shown.length) {
    list.replaceChildren(el('div', { class: 'palette-empty' },
      'Nothing matches. Try a line number such as 12c, part of a description, a file name, or an amount.'));
    return;
  }
  const nodes = [];
  let group = null;
  palette.shown.forEach((item, i) => {
    if (item.type !== group) {
      group = item.type;
      nodes.push(el('div', { class: 'palette-group' },
        { 'Go to': 'Places', Schedule: 'Schedules', Line: 'Lines', Document: 'Documents',
          Decision: 'Open decisions', 'Set aside': 'Set aside' }[group] || group));
    }
    nodes.push(el('button', {
      class: 'palette-item' + (i === palette.active ? ' active' : ''), type: 'button', role: 'option',
      'aria-selected': String(i === palette.active), 'data-i': String(i),
      onclick: () => { closePalette(); item.go(); },
      onmousemove: () => { if (palette.active !== i) { palette.active = i; markActive(); } },
    },
      el('span', { class: 'pi-t' }, item.code ? el('span', { class: 'pi-code' }, item.code) : null, item.label),
      el('span', { class: 'pi-s' }, item.hint || ''),
      (item.amounts || []).length ? el('span', { class: 'pi-n' }, rupees(item.amounts[item.amounts.length - 1])) : null));
  });
  list.replaceChildren(...nodes);
}

function markActive() {
  document.querySelectorAll('.palette-item').forEach((n) => {
    const on = Number(n.dataset.i) === palette.active;
    n.classList.toggle('active', on);
    n.setAttribute('aria-selected', String(on));
    if (on) n.scrollIntoView({ block: 'nearest' });
  });
}

function openPalette() {
  closeMenus();
  // Grouped so results of one kind sit together, places first.
  const rank = { 'Go to': 0, Schedule: 1, Line: 2, Decision: 3, Document: 4, 'Set aside': 5 };
  palette.items = paletteIndex().sort((a, b) => rank[a.type] - rank[b.type]);
  palette.active = 0;
  $('#palette').hidden = false;
  const input = $('#palette-input');
  input.value = '';
  renderPalette();
  input.focus();
}

function closePalette() {
  $('#palette').hidden = true;
}

/* ------------------------------------------------------------------ actions */

/** Ends a reading, a comparison or the sorting that is under way. The
 *  engine is stopped where it is and nothing from that run is saved. */
async function stopWork(key, label) {
  try {
    const out = await api('/api/stop', { method: 'POST', body: JSON.stringify(key ? { key } : { all: true }) })
      .then((r) => r.json());
    if (!out.stopped.length) toast('Nothing was running to stop.');
    else toast(`Stopping ${label || 'everything'}. Nothing from ${out.stopped.length > 1 ? 'those runs' : 'that run'} is saved.`);
  } catch (err) {
    toast(`Could not stop: ${err.message}`, 'err');
  }
}

/** The Stop button that sits beside a run's busy button. */
const stopButton = (key, label) => el('button', {
  class: 'ghost small stop-btn', type: 'button', title: `Stop ${label} now. Nothing from it is saved.`,
  onclick: (e) => { e.currentTarget.disabled = true; stopWork(key, label); },
}, icon('close'), 'Stop');

async function runClassify() {
  if (state.classifying) return;
  state.classifying = true;
  state.classifyLog = [];
  renderHeader();
  renderPanel();
  try {
    const res = await api('/api/classify', {
      method: 'POST',
      body: JSON.stringify({ ay: state.ay, engine: engineId() }),
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const evt = JSON.parse(line);
        state.classifyLog.push(evt);
        if (evt.phase === 'done' && evt.result?.status === 'stopped') {
          toast('Sorting stopped. The documents keep the sorting they had before.');
        }
        const box = document.getElementById('log-classify');
        if (box) {
          box.replaceChildren(...logLines(state.classifyLog));
          box.scrollTop = box.scrollHeight;
        } else if (state.current === 'documents') {
          renderPanel();
        }
        renderHeader();
      }
    }
  } catch (err) {
    state.classifyLog.push({ phase: 'error', detail: err.message });
    toast(`Sorting failed: ${err.message}`, 'err');
  } finally {
    state.classifying = false;
  }
  await refresh().catch(() => renderPanel());
}

async function recompute() {
  if (anythingRunning()) return;
  const before = balance();
  const fresh = $('#fresh');
  fresh.disabled = true;
  try {
    await api('/api/compute', { method: 'POST', body: JSON.stringify({ ay: state.ay }) });
    await refresh();
    toast(balanceChange(before, balance(), 'Recomputed.'));
  } catch (err) {
    toast(`Could not recompute: ${err.message}`, 'err');
  } finally {
    fresh.disabled = false;
  }
}

async function refresh() {
  const data = await getJSON(`/api/state?ay=${state.ay || ''}`);
  state.ay = data.ay;
  state.tabs = data.tabs;
  state.unassigned = data.unassigned || [];
  state.profiles = data.profiles;
  state.activeProfile = data.active_profile;
  state.profileFields = data.profile_fields;
  state.fy = data.fy;
  state.activity = data.activity || { running: [], classifying: false };
  state.handoff = data.handoff || { sheets: [], entered: {} };
  state.version = data.version || '';
  state.sources = data.document_sources || { groups: [], sources: [] };
  state.home = data.home || { path: '', source: '', cloud: [] };
  state.export = data.export || null;
  state.decisions = data.decisions || { current: {}, log: [] };
  state.choices = data.decision_choices || {};
  state.documentMap = data.document_map || null;
  state.engines = data.engines || [];
  state.engineChoices = data.engine_choices || [];
  state.defaultEngine = data.default_engine;
  state.engine = data.engine || data.default_engine;
  state.cache = {};
  // The version this page loaded with; any later difference means the page's
  // own code changed underneath it and what is on screen may be out of date.
  state.pageVersion ||= data.page_version;
  if (data.page_version && data.page_version !== state.pageVersion) showStaleBanner();
  if (data.server_stale) showRestartBanner();

  renderHeader();
  if (!state.current) {
    applyRoute();
  } else {
    renderRail();
    renderPanel();
  }
}

/* ------------------------------------------------------------------- wiring */

$('#profile').addEventListener('change', async (e) => {
  try {
    await api('/api/profiles', { method: 'POST',
                                 body: JSON.stringify({ action: 'activate', id: e.target.value }) });
  } catch (err) {
    // Refused while work is running: its results would land in the other return.
    toast(err.message, 'err');
    e.target.value = state.profiles?.active || '';
    return;
  }
  state.ay = null;
  state.runs = {};
  state.classifyLog = [];
  closeEvidence(true);
  await refresh();
  // Another profile is another return: start it where it is summed up, not
  // on whichever schedule the last one happened to be showing.
  select('home');
});

$('#fresh').addEventListener('click', () => recompute());
$('#search-open').addEventListener('click', () => openPalette());

$('#settings-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  toggleMenu(e.currentTarget, $('#settings-menu'));
});
$('#activity-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  toggleMenu(e.currentTarget, $('#activity-menu'), renderActivity);
});
document.querySelectorAll('[data-theme-choice]').forEach((b) =>
  b.addEventListener('click', () => applyTheme(b.dataset.themeChoice)));
document.addEventListener('click', (e) => {
  if (!e.target.closest('.menu-wrap')) closeMenus();
  if (e.target.closest('.menu a')) closeMenus();
});

$('#palette').addEventListener('mousedown', (e) => { if (e.target === e.currentTarget) closePalette(); });
$('#palette-input').addEventListener('input', () => { palette.active = 0; renderPalette(); });
$('#palette-input').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const n = palette.shown.length;
    if (n) palette.active = (palette.active + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
    markActive();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const item = palette.shown[palette.active];
    if (item) { closePalette(); item.go(); }
  }
});

document.addEventListener('keydown', (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
  if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 'k') {
    e.preventDefault();
    if ($('#palette').hidden) openPalette(); else closePalette();
    return;
  }
  if (e.key === '/' && !typing && $('#palette').hidden && !$('#override-dialog').open) {
    e.preventDefault();
    openPalette();
    return;
  }
  if (e.key === 'Escape') {
    if (!$('#palette').hidden) closePalette();
    else if (document.querySelector('.menu:not([hidden])')) closeMenus();
    else if (evidence && !$('#override-dialog').open) closeEvidence();
  }
});

$('#override-form').addEventListener('submit', async (e) => {
  if (e.submitter?.value !== 'save') return;
  const value = parseInt($('#ov-value').value.replace(/[^\d-]/g, ''), 10);
  const reason = $('#ov-reason').value.trim();
  if (!Number.isFinite(value) || !reason) {
    e.preventDefault();
    return;
  }
  const before = balance();
  try {
    await api('/api/override', {
      method: 'POST',
      body: JSON.stringify({ ay: state.ay, tab: pendingTab, pointer: pendingPointer, value, reason }),
    });
  } catch (err) {
    toast(`The correction was not saved: ${err.message}`, 'err');
    return;
  }
  closeEvidence(true);
  await refresh();
  toast(balanceChange(before, balance(), 'Correction saved.'));
});

window.addEventListener('hashchange', applyRoute);

// A page left open does not ask the server again until something is pressed,
// so check quietly now and then -- only the version, nothing is redrawn.
setInterval(async () => {
  try {
    const data = await getJSON('/api/version');
    if (state.pageVersion && data.page_version && data.page_version !== state.pageVersion) showStaleBanner();
    if (data.server_stale) showRestartBanner();
  } catch { /* the server may be restarting; the next tick will tell */ }
}, 60000);

applyTheme(currentTheme());
refresh().catch((err) => {
  $('#panel').replaceChildren(el('div', { class: 'callout err' }, icon('warn'),
    el('div', {}, el('b', {}, 'Could not reach the local agent'),
       `${err.message}. Start it with: python -m server`)));
});
