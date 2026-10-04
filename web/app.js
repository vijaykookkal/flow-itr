/* ITR-3 assistant - the page.
 *
 * No framework and no build step on purpose: this has to still run years from
 * now, on a machine where nothing has been installed. Plain DOM, one file.
 */

const TOKEN = document.querySelector('meta[name="itr-token"]').content;
const $ = (sel, root = document) => root.querySelector(sel);


const state = {
  schemas: {}, ay: null, tabs: [], current: null, unassigned: [],
  // One entry per schedule: extracting Capital Gains must not grey out Salary.
  runs: {},
  // Re-routing documents is the one job that really does block the others,
  // because every extraction reads the routing it rewrites.
  classifying: false, classifyLog: [],
  // What the server says is running -- survives a page reload, unlike `runs`.
  activity: { running: [], classifying: false },
  // Where you are: an area or a schedule (`current`), and the part of it open.
  sub: null,
  // The figures again as sheets to copy from, and which rows are entered.
  handoff: { sheets: [], entered: {} },
  // What has been settled, with the reason, and the whole log behind it.
  decisions: { current: {}, log: [] },
  choices: {},
  documentMap: null,
  engines: [],
  // Derived lists are rebuilt once per refresh, not once per repaint.
  cache: {},
};

/** This schedule's run: whether it is going, its progress log, its outcome. */
function runOf(tabId) {
  return (state.runs[tabId] ||= { running: false, log: [], lastRun: null });
}

function isRunning(tabId) {
  return runOf(tabId).running || state.activity.running.includes(tabId);
}

function routingBusy() {
  return state.classifying || state.activity.classifying;
}

/* ------------------------------------------------------------------ api */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'X-ITR-Token': TOKEN, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  if (res.status === 403) {
    // The token is now stable across restarts, so this should not happen. If
    // it ever does, reload once to pick up the current one rather than making
    // the person guess why a button stopped working. Guarded so a genuinely
    // rejected token cannot put the page in a reload loop.
    if (!sessionStorage.getItem('itr-token-retry')) {
      sessionStorage.setItem('itr-token-retry', '1');
      location.reload();
      return new Promise(() => {});
    }
    throw new Error('Authentication failed even after reloading. Restart the agent: python -m server');
  }
  sessionStorage.removeItem('itr-token-retry');
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res;
}

const getJSON = (p) => api(p).then((r) => r.json());

/* -------------------------------------------------------------- helpers */

const rupees = (n) =>
  // `|| 0` so a deduction of nil, held as -0, does not print as "-0".
  (typeof n === 'number' ? (Math.round(n) || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 }) : '—');

const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
};

const doc = () => state.tabs.find((t) => t.id === state.current)?.document || null;

const overriddenPointers = () =>
  new Set((doc()?.overrides_applied || []).filter((o) => o.state !== 'stale').map((o) => o.pointer));

/** A clickable money cell. `pointer` addresses the amount inside the document,
 *  which is what an override is keyed on. */
/** "USD 1,520.31" -- an amount as the document stated it in another currency. */
const foreignAmount = (node) =>
  `${node.currency} ${Number(node.amount_foreign).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** A citation is evidence to check, not text to read in the table: a short
 * line under the amount, the whole of it on hover. */
const shortCite = (cite) => {
  if (!cite) return null;
  const [file, ...rest] = String(cite).split('#');
  const name = file.split('/').pop();
  const where = rest.join('#').trim();
  const short = name.length > 26 ? name.slice(0, 24) + '…' : name;
  return el('span', { class: 'cite', title: cite },
    where ? `${short} #${where.length > 18 ? where.slice(0, 16) + '…' : where}` : short);
};

/** A figure that opens its own evidence: how it was reached, the printed line
 *  it came from, what the department holds against it, and where it goes
 *  next. Correcting it is offered from there, beside the evidence, not as the
 *  first thing a click does. */
function figure(text, cls, title, context) {
  const span = el('span', {
    class: cls, title, role: 'button', tabindex: '0',
    onclick: (e) => { e.stopPropagation(); openEvidence({ ...context, anchor: span }); },
    onkeydown: (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      e.stopPropagation();
      openEvidence({ ...context, anchor: span });
    },
  }, text);
  return span;
}

function money(node, pointer) {
  if (!node) return el('td', { class: 'num' }, '—');
  const cite = typeof node === 'object' ? node.cite : null;
  const basis = typeof node === 'object' ? node.basis : null;

  // Stated only in a foreign currency: show it as stated. The rupee figure
  // comes from the rate the law fixes, not from the document, so it is shown
  // where it is computed (the ledger's gain column, the Summary), never here.
  if (typeof node === 'object' && node.amount === undefined && node.currency) {
    return el('td', { class: 'num' },
      figure(foreignAmount(node), 'money foreign', [basis, cite].filter(Boolean).join(' · '),
             { node, cite, basis, amount: node.amount_foreign, foreign: foreignAmount(node) }),
      shortCite(cite));
  }

  const amount = typeof node === 'object' ? node.amount : node;
  const isOverride = Boolean(pointer && overriddenPointers().has(pointer));

  const span = figure(
    rupees(amount),
    'money' + (isOverride ? ' overridden' : ''),
    [basis, cite, isOverride ? 'corrected by you' : null].filter(Boolean).join(' · ')
      || 'Open the evidence for this figure',
    { node, pointer, amount, cite, basis, isOverride });
  return el('td', { class: 'num' }, span, shortCite(cite));
}

const label = (code, text) =>
  el('td', {}, code ? el('span', { class: 'item-label' }, code) : null, text);

const table = (head, rows) =>
  el('div', { class: 'table-wrap' },
    el(
      'table',
      {},
      head ? el('thead', {}, el('tr', {}, head.map((h) => el('th', { class: h.num ? 'num' : '' }, h.t ?? h)))) : null,
      el('tbody', {}, rows)
    ));

/** A row that opens to reveal the rows nested under it.
 *
 * A table cannot hold a <details>, so the disclosure is built by hand. Each
 * branch owns its own rows and its direct children; opening one reveals only
 * the children's own rows, so a grandchild stays hidden until its own parent
 * is opened in turn, and closing one folds the whole subtree away rather than
 * leaving carets pointing at rows nobody can see.
 */
function branch(row, children = []) {
  const rows = [row, ...children.flatMap((c) => c.rows)];
  // A row with nothing under it still answers every call a branch does, so a
  // caller never has to know whether it got children.
  if (!children.length) {
    return { rows, open: false, close() {}, openDeep() {}, show() {}, toggle() {} };
  }

  const self = {
    rows,
    open: false,
    close() {
      self.open = false;
      row.classList.remove('open');
      row.setAttribute('aria-expanded', 'false');
      children.forEach((c) => {
        c.close();
        c.rows.forEach((r) => { r.hidden = true; });
      });
    },
    show() {
      self.open = true;
      row.classList.add('open');
      row.setAttribute('aria-expanded', 'true');
      children.forEach((c) => { c.rows[0].hidden = false; });
    },
    openDeep() {
      self.show();
      children.forEach((c) => {
        c.rows.forEach((r) => { r.hidden = false; });
        c.openDeep();
      });
    },
    toggle() { self.open ? self.close() : self.show(); },
  };

  row.classList.add('opens');
  row.setAttribute('role', 'button');
  row.setAttribute('aria-expanded', 'false');
  row.tabIndex = 0;
  row.firstChild.prepend(el('span', { class: 'caret', 'aria-hidden': 'true' }, '\u25B8'));
  row.addEventListener('click', (e) => {
    // An amount cell opens the override dialog and a button does its own job;
    // only the rest of the row is a disclosure.
    if (e.target.closest('td')?.classList.contains('num')) return;
    if (e.target.closest('button, a, input, select')) return;
    self.toggle();
  });
  row.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); self.toggle(); }
  });
  children.forEach((c) => { c.rows.forEach((r) => { r.hidden = true; }); });
  return self;
}

const card = (title, body, cls = '', aside = null) =>
  el('section', { class: 'card ' + cls }, el('h2', {}, title, aside), body);

/* ------------------------------------------------------------ rendering */

const KB = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);

/** The documents this tab will actually read, and where each came from.
 *
 * A tab used to say "9 document(s) from 3 source(s)" and then list the glob
 * patterns. That hides the only thing worth knowing: which nine files, and was
 * each one opened. A schedule whose totals reconcile perfectly against the
 * documents that WERE read still understates the return if one was skipped.
 */
function documentsCard(tab, d) {
  const docs = tab.documents || [];
  if (!docs.length) {
    return card('Documents', el('div', { class: 'card-body empty' },
      `No document feeds this schedule. Folder rules: ${(tab.resolved_sources || []).join(', ') || 'none'}`));
  }

  // A reading that had trouble with a document says so in a question or a
  // set-aside note. That is a note to go and read, not proof the document went
  // unread: "sheet not read: it belongs to another schedule" is the reading
  // doing its job.
  const gaps = (d?.questions || []).concat(d?.unmapped?.map((u) => `${u.text || ''} ${u.why || ''}`) || []);
  const looksUnread = (name) =>
    gaps.some((g) => typeof g === 'string' && g.includes(name) &&
                     /NOT READ|not covered|could not|unable/i.test(g));

  const rows = docs.map((f) => {
    const unread = looksUnread(f.name);
    const status = !f.read_last_run ? 'Not in the last reading' : unread ? 'Read, with a note' : 'Read';
    const cls = !f.read_last_run ? 'badge' : unread ? 'badge warn' : 'badge pass';
    const big = f.bytes > 20 * 1048576;
    return el('tr', {},
      el('td', {},
         f.name,
         el('span', { class: 'why' }, f.folder),
         f.duplicates?.length
           ? el('span', { class: 'src' }, `${f.duplicates.length} duplicate copy ignored`)
           : null),
      el('td', { class: 'num' }, KB(f.bytes),
         big ? el('span', { class: 'why', style: 'color:var(--warn)' }, 'very large') : null),
      el('td', { class: 'src' }, f.via === 'classifier' ? 'sorted by reading it' : f.via),
      el('td', {}, el('span', { class: cls }, status)));
  });

  const unreadCount = docs.filter((f) => looksUnread(f.name)).length;
  const readCount = docs.filter((f) => f.read_last_run).length;
  return card(
    `Documents analysed (${docs.length})`,
    table(['Document', { t: 'Size', num: true }, 'How it got here', 'Last reading'], rows),
    '',
    el('span', { class: 'src' },
       [readCount ? `${readCount} read in the last reading` : 'not read yet',
        unreadCount ? `${unreadCount} with a note from the reading, listed under Decisions` : null]
         .filter(Boolean).join(' \u00b7 '))
  );
}


async function runReconcile(tab) {
  const run = runOf(tab.id + ':reconcile');
  run.running = true;
  run.log = [];
  renderPanel();
  renderHeader();
  try {
    const res = await api('/api/reconcile', {
      method: 'POST',
      body: JSON.stringify({ ay: state.ay, tab: tab.id, engine: engineId() }),
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
      for (const l of lines) {
        if (!l.trim()) continue;
        const e = JSON.parse(l);
        if (e.phase === 'done') {
          run.log.push({ phase: 'done', detail: e.result.status === 'stopped'
            ? 'stopped; nothing saved' : `${e.result.lines} line(s) compared` });
        } else if (e.phase !== 'tool') {
          run.log.push(e);
        }
        runProgress(tab.id + ':reconcile');
      }
    }
  } catch (err) {
    run.log.push({ phase: 'error', detail: err.message });
  } finally {
    run.running = false;
  }
  await refresh().catch(() => renderPanel());
}


/** What a computed schedule was built from -- schedules, not documents.
 *
 * A derived tab reads nothing itself, so listing the documents routed to it
 * invites the question this card answers instead: which tabs feed it, and are
 * they up to date. */
/** The documents a derived tab's figures actually rest on.
 *
 * They belong to the schedules it was computed from, so they are gathered from
 * those tabs and labelled with which one read them. The questions and unmapped
 * notes come along too, because that is how the documents card knows a file
 * was routed to a schedule and then not read.
 */
function inheritedDocuments(tab, d) {
  const seen = new Set();
  const documents = [];
  const sources = [];
  const merged = { questions: [], unmapped: [] };

  for (const id of d?.derived_from || []) {
    const src = state.tabs.find((t) => t.id === id);
    if (!src) continue;
    sources.push(...(src.resolved_sources || []));
    merged.questions.push(...(src.document?.questions || []));
    merged.unmapped.push(...(src.document?.unmapped || []));
    for (const f of src.documents || []) {
      const key = `${f.name}|${f.bytes}`;
      if (seen.has(key)) continue;          // one document can feed two schedules
      seen.add(key);
      documents.push({ ...f, via: `${src.title} \u00b7 ${f.via || ''}`.trim() });
    }
  }
  return { documents, sources: [...new Set(sources)], merged };
}

function derivedFromCard(tab, d) {
  const from = d?.derived_from || [];
  if (!from.length) {
    return card('Where these figures come from',
      el('div', { class: 'card-body empty' },
         'Computed from other schedules. Press Recompute once they have been read.'));
  }
  const rows = from.map((id) => {
    const src = state.tabs.find((t) => t.id === id);
    const doc = src?.document;
    return el('tr', {},
      el('td', {}, src?.title || id,
         el('span', { class: 'why' }, (src?.schedules || []).join(' · '))),
      el('td', { class: 'num' }, src?.source_count ?? 0),
      el('td', {}, el('span', { class: 'badge ' + (doc ? 'pass' : 'fail') }, doc ? 'Read' : 'Nothing read')),
      el('td', {}, el('button', { class: 'ghost small', onclick: () => select(id) }, 'Open')));
  });
  return card(`Computed from ${from.length} schedule(s)`,
    table(['Schedule', { t: 'Documents', num: true }, 'State', ''], rows),
    from.some((id) => !state.tabs.find((t) => t.id === id)?.document) ? 'warn' : '',
    el('span', { class: 'src' }, 'this schedule reads no documents of its own'));
}

/* ------------------------------------------------- per-schedule renderers */

function renderSalary(d) {
  const out = [];
  const head = computedHead('salary');
  // Section 10 exemptions survive or fall by regime, and the computed head is
  // the only thing that knows which regime was chosen.
  const ruling = new Map((head?.lines || []).map((l) => [`${l.section}|${l.description}`, l]));

  (d.data.employers || []).forEach((e, i) => {
    const p = `/data/employers/${i}`;
    const rows = [];
    const trunks = [];

    // The form prints "(drop down to be provided)" against 1a, 1b and 1c: the
    // breakup is part of the return, not a nicety. Where a document itemises
    // the figure the line opens to it; where none does, there is nothing to
    // open, and that absence is itself worth being able to see.
    const line = (code, text, node, pointer, components, base, refLabel) => {
      const row = el('tr', {}, label(code, text), money(node, pointer));
      if (!components?.length) { rows.push(row); return; }
      const kids = components.map((c, j) => branch(el('tr', { class: 'sub' },
        el('td', {}, el('span', { class: 'payer' }, c.description),
           c.ref ? el('span', { class: 'why' }, `${refLabel} ${c.ref}`) : null),
        money(c.amount, `${base}/${j}/amount/amount`))));
      const trunk = branch(row, kids);
      trunks.push(trunk);
      rows.push(...trunk.rows);
      row.firstChild.append(el('span', { class: 'why' },
        `${components.length} item${components.length === 1 ? '' : 's'}`));
      // A breakup that does not add up to the line above it is a fact about
      // the documents, and hiding it would make the total look verified.
      const sum = components.reduce((a, c) => a + (c.amount?.amount || 0), 0);
      const stated = node?.amount || 0;
      if (Math.abs(sum - stated) > 1) {
        rows.push(el('tr', { class: 'warnrow' },
          el('td', {}, `These ${components.length} items add up to ${rupees(sum)}, not `
                       + `${rupees(stated)} \u2014 a difference of ${rupees(stated - sum)}. `
                       + 'The line above is what the return carries.'),
          el('td', { class: 'num' }, rupees(stated - sum))));
      }
    };

    line('1a', 'Salary as per section 17(1)', e.salary_17_1, `${p}/salary_17_1/amount`,
         e.salary_17_1_components, `${p}/salary_17_1_components`, 'line');
    line('1b', 'Value of perquisites as per section 17(2)', e.perquisites_17_2,
         `${p}/perquisites_17_2/amount`, e.perquisites_17_2_components,
         `${p}/perquisites_17_2_components`, 'Form 12BA serial');
    line('1c', 'Profit in lieu of salary as per section 17(3)', e.profits_in_lieu_17_3,
         `${p}/profits_in_lieu_17_3/amount`);
    rows.push(el('tr', { class: 'total' }, label('1', 'Gross Salary (1a + 1b + 1c)'),
                 money(e.gross_salary, `${p}/gross_salary/amount`)));

    const allowances = e.exempt_allowances || [];
    const exemptTotal = allowances.reduce((a, x) => a + (x.amount?.amount || 0), 0);
    const exemptRow = el('tr', {},
      label('2', 'Less: allowances to the extent exempt under section 10'),
      el('td', { class: 'num' }, rupees(-exemptTotal)));
    if (allowances.length) {
      const kids = allowances.map((a, j) => {
        const verdict = ruling.get(`${a.section}|${a.description}`);
        return branch(el('tr', { class: 'sub' },
          el('td', {}, el('span', { class: 'payer' }, a.description),
             el('span', { class: 'why' },
                verdict && verdict.allowed === false
                  ? `section ${a.section} \u2014 not available under the regime in use, so it is `
                    + 'claimed on the Form 16 but not in this computation'
                  : `section ${a.section}`)),
          money(a.amount, `${p}/exempt_allowances/${j}/amount/amount`)));
      });
      const trunk = branch(exemptRow, kids);
      trunks.push(trunk);
      rows.push(...trunk.rows);
    } else {
      rows.push(exemptRow);
    }

    rows.push(el('tr', { class: 'total' }, label('3', 'Net Salary (1 - 2)'),
                 money(e.net_salary, `${p}/net_salary/amount`)));

    const openAll = el('button', { class: 'linkish', onclick: () => {
      const opening = openAll.dataset.open !== 'yes';
      trunks.forEach((t) => (opening ? t.openDeep() : t.close()));
      openAll.dataset.open = opening ? 'yes' : 'no';
      openAll.textContent = opening ? 'Collapse all' : 'Expand all';
    }, 'data-open': 'no' }, 'Expand all');

    out.push(card(
      e.name,
      table(['Schedule S', { t: 'Amount', num: true }], rows),
      '',
      el('span', { class: 'asides' },
         trunks.length ? openAll : null,
         el('span', { class: 'src' }, [e.tan, e.period].filter(Boolean).join(' \u00b7 ')))));

    if (!e.perquisites_17_2_components?.length && (e.perquisites_17_2?.amount || 0) > 0) {
      out.push(card('The perquisites are not broken down',
        el('div', { class: 'card-body' },
          el('p', { class: 'why', style: 'margin:0' },
            `${rupees(e.perquisites_17_2.amount)} is carried as one figure. Form 12BA itemises `
            + 'perquisites serial by serial and is the document that names an RSU or ESOP '
            + 'perquisite. That naming matters beyond this schedule: the amount taxed here is '
            + 'the cost of acquisition under section 49(2AA) when those shares are sold, so it '
            + 'is what lets Capital Gains be checked. Read this schedule again if a Form 12BA is '
            + 'among the documents.')), 'warn'));
    }
  });

  const dd = d.data.deductions_16 || {};
  const d16 = (dd.standard_16_ia?.amount || 0) + (dd.entertainment_16_ii?.amount || 0)
            + (dd.professional_tax_16_iii?.amount || 0);
  out.push(card(
    'Deductions under section 16, and income chargeable',
    table(['Schedule S', { t: 'Amount', num: true }], [
      el('tr', {}, label('4a', 'Standard deduction under section 16(ia)'),
         money(dd.standard_16_ia, '/data/deductions_16/standard_16_ia/amount')),
      el('tr', {}, label('4b', 'Entertainment allowance under section 16(ii)'),
         money(dd.entertainment_16_ii, '/data/deductions_16/entertainment_16_ii/amount')),
      el('tr', {}, label('4c', 'Tax on employment under section 16(iii)'),
         money(dd.professional_tax_16_iii, '/data/deductions_16/professional_tax_16_iii/amount')),
      el('tr', {}, label('5', 'Total deductions under section 16 (4a + 4b + 4c)'),
         el('td', { class: 'num' }, rupees(d16))),
      el('tr', { class: 'total' },
         label('6', 'Income chargeable under the head \u2018Salaries\u2019 (3 - 5)'),
         money(d.data.income_chargeable, '/data/income_chargeable/amount')),
    ]),
    '',
    el('span', { class: 'src' },
       'Line numbers follow Schedule S for this assessment year; check them against the '
       + 'released utility before filing.')));
  return out;
}

const OS_LABELS = {
  interest_savings: 'Interest — savings account',
  interest_deposits: 'Interest — deposits',
  interest_income_tax_refund: 'Interest on income-tax refund',
  interest_other: 'Interest — other',
  dividend: 'Dividend',
  family_pension: 'Family pension',
  winnings_115BB: 'Winnings taxable under section 115BB',
  other: 'Other',
};

/** The summary tab's copy of a head, which is where the computed form lives. */
function computedHead(name) {
  const summary = state.tabs.find((t) => t.id === 'summary')?.document;
  const regime = summary?.regimes?.[summary?.recommended_regime];
  return regime?.heads?.[name] || null;
}

/** The whole chosen regime, for the schedules that hang off it rather than
 *  off `heads` -- Schedules FSI and TR among them. */
function computedRegime() {
  const summary = state.tabs.find((t) => t.id === 'summary')?.document;
  return summary?.regimes?.[summary?.recommended_regime] || null;
}

function renderOtherSources(d) {
  const out = [];
  const form = computedHead('other_sources')?.form;

  if (form) {
    // Schedule OS, in the order the return numbers it. Each line opens to the
    // payers that make it up: one savings line is two banks, one dividend line
    // is fifty companies, and a reviewer needs to see which.
    const rows = [];
    const trunks = form.normal.map((line) => {
      const lineRow = el('tr', { class: 'itemrow' },
        el('td', {},
           el('span', { class: 'item-label' }, line.item), line.label,
           el('span', { class: 'why' },
              [line.payers.length
                 ? `${line.payers.length} ${line.payers.length === 1 ? 'payer' : 'payers'}`
                 : null,
               line.foreign ? `includes ${rupees(line.foreign)} from foreign payers` : null]
                .filter(Boolean).join(' \u00b7 '))),
        el('td', { class: 'num' }, rupees(line.amount)));

      const payers = line.payers.map((p) => {
        const payerRow = el('tr', { class: 'sub' },
          el('td', {}, el('span', { class: 'payer' }, p.payer),
             el('span', { class: 'why' },
                [p.account, p.count > 1 ? `${p.count} receipts` : null]
                  .filter(Boolean).join(' \u00b7 '))),
          el('td', { class: 'num' }, rupees(p.amount)));

        // A converted receipt opens on its own: each has its own date, so each
        // has its own rate, and a reader has to be able to check them one by
        // one. A rupee receipt has no working, so it has nothing to open.
        const receipts = (p.foreign ? p.receipts : []).map((r) => {
          const w = r.working;
          return branch(el('tr', { class: 'sub2' },
            el('td', {},
               el('span', { class: 'src' }, r.received_on || 'no date'),
               r.stated ? el('span', { class: 'money foreign' },
                             ` ${r.stated.currency} ${Number(r.stated.amount_foreign).toFixed(2)}`) : null,
               w ? el('span', { class: 'fxwork' },
                      `x ${w.rate} \u00b7 SBI TT buy ${w.rate_date}${w.rate_date !== w.date_wanted ? ` (for ${w.date_wanted})` : ''}`) : null),
            el('td', { class: 'num' }, rupees(r.amount))));
        });
        return branch(payerRow, receipts);
      });
      return branch(lineRow, payers);
    });
    trunks.forEach((t) => rows.push(...t.rows));

    rows.push(el('tr', { class: 'total' },
      el('td', {}, el('span', { class: 'item-label' }, '1'), 'Gross income chargeable at normal rates'),
      el('td', { class: 'num' }, rupees(form.gross_normal))));
    if (form.special_total) {
      form.special.forEach((line) => rows.push(el('tr', {},
        el('td', {}, el('span', { class: 'item-label' }, line.item), line.label),
        el('td', { class: 'num' }, rupees(line.amount)))));
    }
    rows.push(el('tr', {},
      el('td', {}, el('span', { class: 'item-label' }, '3'), 'Less: deductions under section 57'),
      el('td', { class: 'num' }, rupees(-form.deductions_57))));
    rows.push(el('tr', { class: 'total' },
      el('td', {}, el('span', { class: 'item-label' }, '6'), 'Net income from other sources'),
      el('td', { class: 'num' }, rupees(form.net))));

    // Receipts the extraction found but could not place belong on this card,
    // with their size: a total that quietly excludes them is the failure this
    // whole tool exists to prevent.
    const unplaced = (d.unmapped || []).filter((u) => u.amount?.amount);
    const unplacedTotal = unplaced.reduce((a, u) => a + u.amount.amount, 0);
    if (unplacedTotal) {
      // "What is this?" is the only sensible response to a large number with
      // no description, so the row carries its own answer rather than sending
      // the reader to another card to find out.
      const kids = unplaced.map((u) => branch(el('tr', { class: 'sub' },
        el('td', {},
           el('span', { class: 'payer', title: u.text || '' },
              (u.text || '').length > 96 ? (u.text || '').slice(0, 94) + '\u2026' : (u.text || '')),
           el('span', { class: 'why', title: u.why || '' },
              (u.why || '').length > 160 ? (u.why || '').slice(0, 158) + '\u2026' : (u.why || '')),
           el('span', { class: 'src' }, u.source || '')),
        el('td', { class: 'num' }, rupees(u.amount.amount)))));
      const head = el('tr', { class: 'warnrow' },
        el('td', {}, 'Credits found but not placed on any line',
           el('span', { class: 'why' },
              `${unplaced.length} credit(s) whose nature the document does not state — `
              + 'not counted as income here, and not written off either')),
        el('td', { class: 'num' }, rupees(unplacedTotal)));
      const trunk = branch(head, kids);
      rows.push(...trunk.rows);
      trunks.push(trunk);
    }

    const openAll = el('button', { class: 'linkish', onclick: () => {
      const opening = openAll.dataset.open !== 'yes';
      trunks.forEach((t) => (opening ? t.openDeep() : t.close()));
      openAll.dataset.open = opening ? 'yes' : 'no';
      openAll.textContent = opening ? 'Collapse all' : 'Expand all';
    }, 'data-open': 'no' }, 'Expand all');
    out.push(card('Schedule OS', table(['Item', { t: 'Amount', num: true }], rows),
                  unplacedTotal ? 'warn' : '',
                  el('span', { class: 'asides' }, openAll,
                     el('span', { class: 'src' }, form.verify))));

    if (form.pending?.length) {
      out.push(card(
        `${form.pending.length} receipt(s) are not in these figures`,
        el('div', { class: 'card-body' },
          el('p', { style: 'margin:0 0 10px' },
            'These were paid in a foreign currency. Rule 115 converts them at the rate for the ' +
            'month before they were received, so each one needs its date of receipt — and, where ' +
            'the date is known, that day’s rate. Until then they are left out rather than counted ' +
            'at zero.'),
          table(['Payer', 'Stated', 'What is missing'],
            form.pending.map((p) => el('tr', {},
              el('td', {}, p.payer, el('span', { class: 'why' }, `Schedule OS item ${p.item}`)),
              el('td', { class: 'num' }, `${p.currency} ${Number(p.amount_foreign).toFixed(2)}`),
              el('td', { class: 'why' }, p.why))))),
        'err'));
    }

    // The extraction can only total the rupee rows: a receipt in dollars has
    // no rupee figure until Rule 115 is applied to its own date, and that
    // happens here, not there. So the two totals are expected to differ by
    // exactly the converted foreign income, and saying "they differ" without
    // doing that arithmetic reports a discrepancy that is not one.
    if (form.stated_gross) {
      const converted = form.normal.reduce((a, l) => a + (l.foreign || 0), 0);
      const residual = form.gross_normal - form.stated_gross - converted;
      if (Math.abs(form.stated_gross - form.gross_normal) > 1) {
        const settled = Math.abs(residual) <= 100;
        out.push(card(
          settled ? 'Why this differs from the extraction’s own total'
                  : 'The extraction’s own total does not reconcile',
          el('div', { class: 'card-body' },
            table(['', { t: 'Amount', num: true }], [
              el('tr', {}, el('td', {}, 'Stated by the extraction, rupee rows only'),
                 el('td', { class: 'num' }, rupees(form.stated_gross))),
              el('tr', {}, el('td', {}, 'Add: foreign receipts, converted under Rule 115'),
                 el('td', { class: 'num' }, rupees(converted))),
              el('tr', { class: 'total' }, el('td', {}, 'These lines'),
                 el('td', { class: 'num' }, rupees(form.gross_normal))),
              el('tr', { class: residual && !settled ? 'warnrow' : '' },
                 el('td', {}, residual ? 'Still unexplained' : 'Reconciles exactly'),
                 el('td', { class: 'num' }, rupees(residual))),
            ]),
            el('p', { class: 'why', style: 'margin:10px 0 0' },
               settled
                 ? 'The extraction totals only what it could total. A receipt in a foreign '
                   + 'currency has no rupee figure until Rule 115 is applied to its own date of '
                   + 'receipt, which is done here, receipt by receipt. The difference is that '
                   + 'conversion'
                   + (residual ? `, leaving ${rupees(Math.abs(residual))} unaccounted — small `
                                 + 'enough to be a rounding or classification difference on a '
                                 + 'receipt of a few rupees, but it is shown rather than hidden.'
                               : ' and nothing else.')
                 : 'This gap is not the foreign conversion. Something in the ledger is not in '
                   + 'the extraction\u2019s total, or the other way round, and the lines above '
                   + 'are the ones computed row by row.')),
          settled ? '' : 'warn'));
      }
    }
  }

  const items = d.data.items || [];
  const rows = items.map((it, i) =>
    el('tr', {},
      el('td', {}, it.payer, it.account_ref ? el('span', { class: 'why' }, it.account_ref) : null),
      el('td', { class: 'src' }, it.received_on || '—'),
      el('td', {}, OS_LABELS[it.category] || it.category),
      money(it.amount, `/data/items/${i}/amount/amount`),
      money(it.tds_deducted, `/data/items/${i}/tds_deducted/amount`)));
  rows.push(el('tr', { class: 'total' },
    el('td', { colspan: 3 }, 'Gross income from other sources, as read from the documents'),
    money(d.data.gross_income_from_os, '/data/gross_income_from_os/amount'),
    money({ amount: items.reduce((s, i) => s + (i.tds_deducted?.amount || 0), 0) })));
  out.push(card(`Ledger (${items.length})`,
    table(['Payer', 'Received', 'Category', { t: 'Amount', num: true }, { t: 'TDS', num: true }], rows),
    '', el('span', { class: 'src' }, 'the evidence behind each line above')));
  return out;
}

function renderDeductions(d) {
  const rows = (d.data.claims || []).map((c, i) =>
    el(
      'tr',
      {},
      el('td', {}, c.section),
      el('td', {}, c.description, c.payee_pan ? el('span', { class: 'why' }, `PAN ${c.payee_pan}${c.donation_arn ? ' · ARN ' + c.donation_arn : ''}`) : null),
      money(c.amount, `/data/claims/${i}/amount/amount`)
    )
  );
  rows.push(el('tr', { class: 'total' }, el('td', { colspan: 2 }, 'Total claimed before statutory ceilings'), money(d.data.total_claimed, '/data/total_claimed/amount')));
  return [
    card('Schedule VI-A: what the proofs evidence', table(['Section', 'Proof', { t: 'Amount', num: true }], rows), '', el('span', { class: 'src' }, 'statutory ceilings are applied in the Computation, where each is shown')),
  ];
}

function renderTaxesPaid(d) {
  const out = [];
  const mk = (title, rows, cols) => rows.length && out.push(card(title, table(cols, rows)));

  mk(
    'Schedule TDS1 — tax deducted on salary',
    (d.data.tds_salary || []).map((r, i) =>
      el('tr', {}, el('td', {}, r.deductor), el('td', { class: 'src' }, r.tan), money(r.income_paid, `/data/tds_salary/${i}/income_paid/amount`), money(r.tds, `/data/tds_salary/${i}/tds/amount`))
    ),
    ['Deductor', 'TAN', { t: 'Income paid', num: true }, { t: 'TDS', num: true }]
  );

  mk(
    'Schedule TDS2 — tax deducted on income other than salary',
    (d.data.tds_other || []).map((r, i) =>
      el('tr', {}, el('td', {}, r.deductor), el('td', { class: 'src' }, `${r.tan_or_pan || ''} · ${r.section || ''}`), money(r.gross_amount, `/data/tds_other/${i}/gross_amount/amount`), money(r.tds, `/data/tds_other/${i}/tds/amount`))
    ),
    ['Deductor', 'TAN · section', { t: 'Gross', num: true }, { t: 'TDS', num: true }]
  );

  mk(
    'Schedule IT — advance tax and self-assessment tax',
    (d.data.taxes_paid_challans || []).map((c, i) =>
      el('tr', {}, el('td', { class: 'src' }, c.bsr_code), el('td', {}, c.date_of_deposit), el('td', { class: 'src' }, c.challan_no), el('td', {}, c.kind?.replace('_', ' ')), money(c.amount, `/data/taxes_paid_challans/${i}/amount/amount`))
    ),
    ['BSR code', 'Deposited', 'Challan', 'Kind', { t: 'Amount', num: true }]
  );

  out.push(card('Total taxes paid', table(null, [el('tr', { class: 'total' }, el('td', {}, 'Credit claimed in this return'), money(d.data.total_taxes_paid, '/data/total_taxes_paid/amount'))])));
  return out;
}

/** One stage of the computation: its table, then why it did that. */
function stageCard(st) {
  const body = [];
  if (st.table) {
    const numeric = st.table.columns.map((h, i) =>
      i > 0 && st.table.rows.some((r) => typeof r[i] === 'number'));
    body.push(table(
      st.table.columns.map((h, i) => (numeric[i] ? { t: h, num: true } : h)),
      st.table.rows.map((row) => {
        const isTotal = /^(Total income|Gross total income|Gross tax liability|Aggregate liability|Amount payable|Payable|Refund)/i.test(String(row[1] ?? row[0]));
        // A line like 3ii or 4aiii is a sub-line of the one above it. The form
        // indents those, and a 39-row Part B-TI is unreadable if they all sit flush.
        const isSub = st.table.columns[0] === 'Line' && /^\d+[a-z]/i.test(String(row[0] ?? ''));
        const isLine = st.table.columns[0] === 'Line';
        return el('tr', { class: [isTotal ? 'total' : '', isSub ? 'sub' : ''].join(' ').trim() },
          row.map((cell, i) => {
            if (typeof cell === 'number') {
              // A line of Part B-TI or Part B-TTI opens to where it came from
              // and to the same line of the filed return, if there is one.
              return el('td', { class: 'num' + (cell < 0 ? ' neg' : '') },
                isLine
                  ? figure(rupees(cell), 'money', 'Open the evidence for this line',
                           { amount: cell, computed: true,
                             line: { part: st.code, item: String(row[0] ?? ''), label: String(row[1] ?? '') } })
                  : rupees(cell));
            }
            return el('td', { class: i === 0 && st.table.columns[0] === 'Line' ? 'ln' : '' }, String(cell ?? ''));
          }));
      })));
  }
  if (st.notes?.length) {
    body.push(el('details', { class: 'why-box' },
      el('summary', {}, `Why — ${st.notes.length} note${st.notes.length > 1 ? 's' : ''}`),
      el('ol', { class: 'why-list' }, st.notes.map((n) => el('li', {}, n)))));
  }
  return card(
    el('span', { class: 'stage-title' },
       el('span', { class: 'stage-no' }, String(st.no)),
       el('span', { class: 'sch' }, st.code),
       st.title),
    el('div', { class: 'stage-body' + (st.skipped ? ' skip' : '') }, ...body),
    '',
    el('span', { class: 'src' }, st.purpose)
  );
}

const FILED_STATE = {
  agrees: ['agrees', 'badge pass'],
  sign_only: ['agrees (sign shown differently)', 'badge pass'],
  differs: ['differs', 'badge fail'],
  not_in_filed: ['not on the filed return', 'badge'],
  not_in_computed: ['not produced here', 'badge'],
};

// The headings the form prints above a group of sub-lines. They carry no
// amount of their own, so they exist nowhere in either side's figures and have
// to be named here. Anything not listed falls back to "Item n", which is
// correct if plain -- better a dull heading than a wrong one.
const FILED_HEADINGS = {
  'Part B-TI': {
    3: 'Profits and gains from business or profession',
    4: 'Capital gains',
    5: 'Income from other sources',
    12: 'Deduction under chapter VI-A',
  },
  'Part B-TTI': {
    1: 'Tax payable on deemed total income under section 115JC',
    2: 'Tax payable on total income',
    6: 'Tax relief',
    8: 'Interest and fee payable',
    10: 'Taxes Paid',
  },
  'Taxes paid': { 10: 'Taxes Paid' },
};

/** The item a line sits under: '4ai' and '4bi' both belong to item 4.
 *
 * Some rows carry no number of their own -- the surcharge is printed as Ai,
 * Aii, Bi, Bii inside item 2g -- so a row without one stays with the item
 * above it, which is where the form puts it. */
function groupOf(item, carried) {
  const m = String(item ?? '').match(/^\s*(\d+)/);
  return m ? m[1] : carried;
}

/** What was filed, set beside what this tool computes.
 *
 * The lines stay in the order the form prints them. An earlier version sorted
 * them into "differences", "unpaired" and "agrees", which made the differences
 * easy to find and destroyed the thing that makes a return readable: a figure
 * means what the line above and below it say it means, and 2f out of sequence
 * is just a number. Items collapse instead, and an item holding a difference
 * opens itself. */
function filedComparison(cmp) {
  const out = [];
  if (cmp.warnings?.length) {
    out.push(card('Before you read this comparison',
      el('div', { class: 'card-body' },
        el('ul', { class: 'plain' }, cmp.warnings.map((x) => el('li', {}, x)))), 'warn'));
  }

  const cellsFor = (r) => {
    const [text, cls] = FILED_STATE[r.state] || [r.state, 'badge'];
    return [
      el('td', {}, el('span', { class: 'item-label' }, r.item), r.label,
         r.filed_label && r.filed_label !== r.label
           ? el('span', { class: 'why' }, `filed as: ${r.filed_label}`) : null),
      el('td', { class: 'num' }, r.computed === null ? '\u2014' : rupees(r.computed)),
      el('td', { class: 'num' }, r.filed === null ? '\u2014' : rupees(r.filed)),
      el('td', { class: 'num' + (r.difference ? ' neg' : '') },
         r.difference === null ? '\u2014' : rupees(r.difference)),
      el('td', {}, el('span', { class: cls }, text)),
    ];
  };

  Object.entries(cmp.parts).forEach(([part, result]) => {
    if (!result.rows.length) return;

    // Group in printed order, never reordered.
    const groups = [];
    let carried = null;
    for (const r of result.rows) {
      const key = groupOf(r.item, carried);
      carried = key;
      let g = groups.find((x) => x.key === key);
      if (!g) { g = { key, head: null, kids: [] }; groups.push(g); }
      if (String(r.item).trim() === String(key) && !g.head) g.head = r;
      else g.kids.push(r);
    }

    const rows = [];
    const trunks = [];
    for (const g of groups) {
      const bad = [g.head, ...g.kids].filter((r) => r && r.state === 'differs').length;
      const lines = (g.head ? 1 : 0) + g.kids.length;

      if (!g.kids.length) {                       // a line with nothing under it
        const r = g.head || null;
        if (r) rows.push(el('tr', { class: r.state === 'differs' ? 'warnrow' : '' },
                            ...cellsFor(r)));
        continue;
      }

      const headCells = g.head
        ? cellsFor(g.head)
        : [el('td', {}, el('span', { class: 'item-label' }, g.key),
             FILED_HEADINGS[part]?.[g.key] || `Item ${g.key}`),
           el('td', { class: 'num' }, '\u2014'), el('td', { class: 'num' }, '\u2014'),
           el('td', { class: 'num' }, '\u2014'), el('td', {})];
      headCells[0].append(el('span', { class: 'why' },
        `${lines} line${lines === 1 ? '' : 's'}`
        + (bad ? ` \u00b7 ${bad} differ${bad === 1 ? 's' : ''}` : ' \u00b7 all agree')));
      const head = el('tr', { class: bad ? 'itemrow warnrow' : 'itemrow' }, ...headCells);

      const trunk = branch(head, g.kids.map((r) => branch(
        // a sub-line stays indented under its item whether or not it differs
        el('tr', { class: r.state === 'differs' ? 'sub warnrow' : 'sub' }, ...cellsFor(r)))));
      trunks.push(trunk);
      rows.push(...trunk.rows);
      if (bad) trunk.show();     // an item holding a difference opens itself
    }

    const openAll = el('button', { class: 'linkish', onclick: () => {
      const opening = openAll.dataset.open !== 'yes';
      trunks.forEach((t) => (opening ? t.openDeep() : t.close()));
      openAll.dataset.open = opening ? 'yes' : 'no';
      openAll.textContent = opening ? 'Collapse all' : 'Expand all';
    }, 'data-open': 'no' }, 'Expand all');

    const counts = result.counts;
    out.push(card(
      `${part}: computed against filed`,
      table([part, { t: 'Computed', num: true }, { t: 'Filed', num: true },
             { t: 'Difference', num: true }, ''], rows),
      counts.differs ? 'warn' : '',
      el('span', { class: 'asides' }, trunks.length ? openAll : null,
         el('span', { class: 'src' },
            `${counts.agrees} agree \u00b7 ${counts.differs} differ \u00b7 `
            + `${counts.not_in_filed + counts.not_in_computed} unpaired`))));
  });

  if (cmp.unpaired) {
    out.push(card('About the unpaired lines',
      el('div', { class: 'card-body' },
         el('p', { class: 'why', style: 'margin:0' }, cmp.note)), ''));
  }
  return out;
}

function renderSummary(s) {
  const out = [];

  if (s.unavailable) {
    return [card('No computation for this year yet',
      el('div', { class: 'card-body' },
         el('p', { style: 'margin:0 0 8px' }, s.unavailable),
         el('p', { class: 'why', style: 'margin:0' }, s.warning)), 'warn')];
  }

  const chosen = s.regimes[s.recommended_regime];
  const c = chosen.cascade;
  // The balance is on the Summary page and the filed return is under Reconcile;
  // this page is the working, stage by stage.
  if (c) c.stages.forEach((st) => out.push(stageCard(st)));

  // The other regime, for the one decision this page exists to support.
  const other = s.recommended_regime === 'new' ? 'old' : 'new';
  // Both columns come from the staged computation; there is no other.
  const line = (label, key) =>
    el('tr', {}, el('td', {}, label),
       el('td', { class: 'num' }, rupees(chosen.cascade?.totals[key])),
       el('td', { class: 'num' }, rupees(s.regimes[other].cascade?.totals[key])));
  out.push(card(
    'The other regime, for comparison',
    table([' ', { t: s.recommended_regime === 'new' ? 'New regime' : 'Old regime', num: true },
           { t: other === 'new' ? 'New regime' : 'Old regime', num: true }],
      [line('Total income', 'total_income'),
       line('Tax at slab rates', 'tax_at_slab'),
       line('Tax at special rates', 'tax_at_special'),
       line('Rebate under section 87A', 'rebate_87a'),
       line('Surcharge', 'surcharge'),
       line('Cess', 'cess'),
       el('tr', { class: 'total' }, el('td', {}, 'Total tax liability'),
          el('td', { class: 'num' }, rupees(chosen.cascade?.totals.total_tax_liability)),
          el('td', { class: 'num' }, rupees(s.regimes[other].cascade?.totals.total_tax_liability)))]),
    '',
    el('span', { class: 'src' },
       s.regime_is_elected
         ? `You have elected the ${s.recommended_regime} regime; the election costs ${rupees(s.election_costs)}`
         : `${rupees(s.saving_versus_other)} cheaper`)));

  const cgd = chosen.capital_gains?.disagreements || [];
  if (cgd.length) {
    out.push(card(`Capital gains: ${cgd.length} row(s) disagree with the document`,
      el('div', { class: 'card-body' },
         el('ul', { class: 'plain' }, cgd.slice(0, 20).map((x) => el('li', {}, x)))), 'warn'));
  }

  const failed = (s.checks || []).filter((x) => !x.ok);
  out.push(card(
    `Cross-checks (${failed.length} of ${s.checks.length} disagree)`,
    el('div', { class: 'card-body' },
       s.checks.map((x) =>
         el('div', { class: 'check' },
            el('span', { class: 'badge ' + (x.ok ? 'pass' : 'fail') }, x.ok ? 'agrees' : 'differs'),
            el('div', {}, el('div', {}, x.check), el('div', { class: 'detail' }, x.detail))))),
    failed.length ? 'err' : ''));

  out.push(card(
    'Not included in the figures above',
    el('div', { class: 'card-body' }, el('ul', { class: 'plain' }, s.not_implemented.map((n) => el('li', {}, n)))),
    'warn',
    el('span', { class: 'src' }, 'read this before trusting the balance')));

  out.push(card('Status', el('div', { class: 'card-body' }, s.warning), 'warn'));
  return out;
}

function renderGeneric(d) {
  return [card('Raw document', el('pre', { class: 'card-body log' }, JSON.stringify(d.data, null, 2)))];
}


const CG_ASSET = {
  equity_stt: 'Listed equity / equity MF (STT paid)',
  equity_unlisted: 'Unlisted equity',
  debt_mf_specified: 'Specified MF (s.50AA)',
  debt_mf_other: 'Other debt fund',
  bonds_debentures: 'Bonds / debentures',
  immovable_property: 'Immovable property',
  gold_jewellery: 'Gold / jewellery',
  foreign_shares: 'Foreign shares',
  other: 'Other',
};


function cgFormSection(title, rows, totalItem) {
  const body = rows
    .filter((r) => r.rows || r.item === totalItem)
    .map((r) =>
      el('tr', { class: r.item === totalItem ? 'total' : '' },
         el('td', {}, el('span', { class: 'item-label' }, r.item), r.label),
         el('td', { class: 'num' }, rupees(r.sell_value)),
         el('td', { class: 'num' }, rupees(r.buy_value)),
         el('td', { class: 'num' }, rupees(r.expenses)),
         el('td', { class: 'num' }, rupees(r.gain))));
  return card(
    title,
    table(['Item', { t: 'Sell value', num: true }, { t: 'Buy value', num: true },
           { t: 'Expenses', num: true }, { t: 'Gain after exp.', num: true }], body)
  );
}

function renderCgForm(form) {
  const out = [];
  out.push(cgFormSection('Schedule CG — A. Short-term capital gain', form.short_term, 'A10'));
  out.push(cgFormSection('Schedule CG — B. Long-term capital gain', form.long_term, 'B13'));

  out.push(card('Schedule CG — C. Total',
    table(['Item', { t: 'Sell value', num: true }, { t: 'Buy value', num: true },
           { t: 'Expenses', num: true }, { t: 'Gain after exp.', num: true }],
      [el('tr', { class: 'total' },
          el('td', {}, el('span', { class: 'item-label' }, form.total.item), form.total.label),
          el('td', { class: 'num' }, rupees(form.total.sell_value)),
          el('td', { class: 'num' }, rupees(form.total.buy_value)),
          el('td', { class: 'num' }, rupees(form.total.expenses)),
          el('td', { class: 'num' }, rupees(form.total.gain)))])));

  out.push(card(
    'Quarterly break-up for advance tax (section 234C)',
    table(['Period', { t: '111A STCG', num: true }, { t: 'Other STCG', num: true },
           { t: '112A LTCG', num: true }, { t: 'Other LTCG', num: true }],
      form.quarters.map((q) =>
        el('tr', {},
           el('td', {}, q.label),
           el('td', { class: 'num' }, rupees(q.stcg_111a)),
           el('td', { class: 'num' }, rupees(q.stcg_other)),
           el('td', { class: 'num' }, rupees(q.ltcg_112a)),
           el('td', { class: 'num' }, rupees(q.ltcg_other))))),
    '',
    el('span', { class: 'src' }, 'split by transfer date; negatives shown as nil')));

  if (form.quarter_notes?.length) {
    out.push(card('Notes on the break-up',
      el('div', { class: 'card-body' },
         el('ul', { class: 'plain' }, form.quarter_notes.map((n) => el('li', {}, n)))), 'warn'));
  }

  out.push(card('Before filing',
    el('div', { class: 'card-body' }, el('div', { class: 'why' }, form.verify)), 'warn'));
  return out;
}

/** A rate the return needs and no document supplies, with a place to enter it. */
function rateNeededCard(cg) {
  const needed = cg?.rates_needed || [];
  const missing = cg?.unconverted || [];
  if (!missing.length) return null;

  const rows = needed.map((n) => {
    const input = el('input', { type: 'number', step: '0.0001', min: '0', placeholder: 'e.g. 83.1500', style: 'width:9em' });
    const status = el('span', { class: 'src' });
    const save = el('button', {
      onclick: async () => {
        save.disabled = true;
        status.textContent = 'saving…';
        try {
          await api('/api/fx', { method: 'POST', body: JSON.stringify({ ay: state.ay, currency: n.currency, date: n.date, rate: input.value }) });
          await refresh();
        } catch (err) {
          status.textContent = err.message;
          save.disabled = false;
        }
      },
    }, 'Save rate');
    return el('tr', {},
      el('td', {}, `${n.currency} on ${n.date}`),
      el('td', { class: 'num' }, n.rows),
      el('td', {}, input, ' ', save, ' ', status));
  });

  // The lookup runs the engine with web access to the rate archive only and
  // none of your documents; each rate it finds is checked against its source.
  const lookupLog = el('div', { class: 'log', style: 'display:none;margin:10px 0 0' });
  const lookup = el('button', {
    class: 'primary',
    onclick: async () => {
      lookup.disabled = true;
      lookup.textContent = 'Looking up…';
      lookupLog.style.display = '';
      lookupLog.replaceChildren();
      const line = (e) => lookupLog.append(
        el('div', {}, el('span', { class: 'ph ' + e.phase }, e.phase), el('span', {}, e.detail || '')));
      try {
        const res = await api('/api/fx/lookup', {
          method: 'POST', body: JSON.stringify({ ay: state.ay, engine: engineId() }) });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const l of lines) {
            if (!l.trim()) continue;
            const e = JSON.parse(l);
            if (e.phase === 'done') {
              line({ phase: 'done', detail: `${e.result.saved} rate(s) verified and saved` });
              for (const q of e.result.questions || []) line({ phase: 'note', detail: q });
            } else if (e.phase !== 'tool' || /WebFetch/.test(e.detail || '')) {
              line(e);
            }
          }
        }
        await refresh();
      } catch (err) {
        line({ phase: 'error', detail: err.message });
      } finally {
        lookup.disabled = false;
        lookup.textContent = 'Look up rate';
      }
    },
  }, 'Look up rate');

  return card(
    `${missing.length} disposal(s) are not in any total yet`,
    el('div', { class: 'card-body' },
      el('p', { style: 'margin:0 0 10px' },
        'These were sold in a foreign currency. Rule 115 converts them at the State Bank of India ' +
        'telegraphic-transfer buying rate on the last day of the month before the sale, and they stay ' +
        'out of every figure below until that rate is in — counting the sale at zero would misstate ' +
        'the gain or loss. The rate is looked up automatically after a reading; if that did not ' +
        'happen or failed, look it up now.'),
      el('div', {}, lookup),
      lookupLog,
      el('p', { class: 'why', style: 'margin:14px 0 6px' }, 'Or enter a published rate yourself:'),
      table(['Rate needed', { t: 'Rows', num: true }, 'SBI TT buying rate (₹ per unit)'], rows),
      el('p', { class: 'why', style: 'margin:10px 0 0' },
        'If that date was a holiday, the rule uses the nearest earlier working day. Check with ' +
        'whoever signs the return whether the cost should use the same date.')),
    'err');
}

/** A rupee value in the ledger, with how it was reached.
 *
 * Stated in rupees: the amount, clickable to correct, with its citation.
 * Stated in a foreign currency: the converted rupees, and under them the
 * working -- "USD 1,520.31 × 87.70 · 30-08-2025" -- with the rule on hover, so
 * the multiplication can be checked against the rate card. */
function rupeeCell(node, computedRupees, fxWork, pending, pointer, reason, note) {
  const isForeign = node && typeof node === 'object' && node.amount === undefined && node.currency;
  if (!isForeign) {
    const cell = money(node, pointer);
    if (reason && computedRupees !== undefined && node?.amount !== computedRupees) {
      // The cost the return uses is not the figure the document printed: the
      // charges paid on purchase were added, or grandfathering replaced it.
      // Said in the cell, because a gain that does not follow from the two
      // figures beside it looks like a mistake.
      // Two short lines, each of which fits the column: what was added, then
      // the cost the gain is worked from.
      (note || [`used ${rupees(computedRupees)}`]).forEach((line) =>
        cell.append(el('span', { class: 'fxwork', title: reason, style: 'white-space:nowrap' }, line)));
    }
    return cell;
  }
  if (pending || !fxWork) {
    return el('td', { class: 'num' },
      el('span', { class: 'money foreign' }, foreignAmount(node)),
      el('span', { class: 'cite', style: 'color:var(--err)' }, 'rate needed'));
  }
  const rateNote = fxWork.rate_date === fxWork.date_wanted
    ? `${fxWork.rule} (${fxWork.rate_date})`
    : `${fxWork.rule}: ${fxWork.date_wanted} had no rate, so ${fxWork.rate_date}`;
  return el('td', { class: 'num', title: [rateNote, node.cite].filter(Boolean).join('\n') },
    el('span', { class: 'money' }, rupees(computedRupees)),
    el('span', { class: 'fxwork' },
      `${foreignAmount(node)} × ${fxWork.rate.toFixed(2)}`),
    el('span', { class: 'fxwork' }, `SBI TT buy · ${fxWork.rate_date}`));
}

function renderCapitalGains(d) {
  const out = [];
  const summary = state.tabs.find((t) => t.id === 'summary')?.document;
  const cg = summary?.regimes?.[summary?.recommended_regime]?.capital_gains;

  // What is missing from the totals comes before the totals themselves.
  const rateCard = rateNeededCard(cg);
  if (rateCard) out.push(rateCard);

  // The form next: this is what gets typed into the utility. The ledger
  // below it is the evidence for each line.
  if (cg?.form) out.push(...renderCgForm(cg.form));
  const rows = d.data.disposals || [];

  // Each ledger row's computed figures, by its position in the ledger.
  const computed = {};
  for (const r of cg?.rows || []) computed[r.index] = r;
  const pending = {};
  for (const u of cg?.unconverted || []) pending[u.index] = u;

  // Per-asset-class summary first: the ledger can run to thousands of rows and
  // nobody checks a return by reading every trade.
  const byClass = {};
  rows.forEach((r, i) => {
    const b = (byClass[r.asset_class] = byClass[r.asset_class] || { n: 0, proceeds: 0, cost: 0, pending: 0 });
    b.n += 1;
    if (pending[i]) { b.pending += 1; return; }
    const c = computed[i];
    b.proceeds += c ? c.proceeds : r.full_value?.amount || 0;
    b.cost += c ? c.cost : r.cost_of_acquisition?.amount || 0;
  });
  out.push(
    card(
      'Disposals by asset class',
      table(
        ['Asset class', { t: 'Rows', num: true }, { t: 'Proceeds', num: true }, { t: 'Cost', num: true }],
        Object.entries(byClass).map(([k, b]) =>
          el('tr', {},
             el('td', {}, CG_ASSET[k] || k,
                b.pending ? el('span', { class: 'why', style: 'color:var(--err)' },
                               `${b.pending} not counted: rate needed`) : null),
             el('td', { class: 'num' }, b.n),
             el('td', { class: 'num' }, rupees(b.proceeds)),
             el('td', { class: 'num' }, rupees(b.cost))))
      ),
      '',
      el('span', { class: 'src' }, `${rows.length} disposal(s)`)
    )
  );

  const totals = d.data.totals || {};
  if (Object.keys(totals).length) {
    out.push(
      card('Totals the documents state',
        table(['Figure', { t: 'Amount', num: true }],
          Object.entries(totals).map(([k, v]) =>
            el('tr', {}, el('td', {}, k.replace('stated_', '').replace(/_/g, ' ')),
               money(v, `/data/totals/${k}/amount`)))),
        '', el('span', { class: 'src' }, 'for reconciliation only: the Computation works out its own'))
    );
  }

  if ((d.data.deductions || []).length) {
    out.push(card('Exemptions claimed',
      table(['Section', 'Detail', { t: 'Amount', num: true }],
        d.data.deductions.map((x, i) =>
          el('tr', {}, el('td', {}, x.section), el('td', {}, x.description || ''),
             money(x.amount, `/data/deductions/${i}/amount/amount`))))));
  }

  // The ledger itself, newest first, capped: the file is the full record.
  const shown = rows.slice(0, 60);
  out.push(
    card(
      `Ledger${rows.length > shown.length ? ` (first ${shown.length} of ${rows.length})` : ''}`,
      el('div', { class: 'ledger' }, table(
        ['Description',
         // One column, because the pair is one fact: how long it was held.
         // The heading stacks the same way the dates under it do.
         el('span', { class: 'th-stack' }, el('span', {}, 'Acquired'), el('span', {}, 'Transferred')),
         { t: 'Sell value ₹', num: true }, { t: 'Buy value ₹', num: true },
         { t: 'Expenses ₹', num: true }, { t: 'Gain ₹', num: true }, 'Term'],
        shown.map((r, i) => {
          const c = computed[i];
          const p = pending[i];
          return el('tr', {},
             el('td', { class: 'desc' }, r.description || '', r.isin ? el('span', { class: 'why' }, r.isin) : null),
             el('td', { class: 'dates' },
                el('span', {}, r.acquired_on || '—'),
                el('span', {}, r.transferred_on || '—')),
             rupeeCell(r.full_value, c?.proceeds, c?.fx?.full_value, p, `/data/disposals/${i}/full_value/amount`),
             rupeeCell(r.cost_of_acquisition, c?.cost, c?.fx?.cost_of_acquisition, p,
                       `/data/disposals/${i}/cost_of_acquisition/amount`, c?.cost_reason,
                       // The charges paid on purchase are part of the cost: say so in
                       // the cell, with the cost the gain is actually worked from.
                       c?.purchase_expenses && c.cost === c.cost_stated + c.purchase_expenses
                         ? [`+${rupees(c.purchase_expenses)} charges`, `cost ${rupees(c.cost)}`]
                         : null),
             el('td', { class: 'num' }, c ? rupees(c.expenses) : '—',
                c?.stt ? el('span', { class: 'fxwork',
                                      title: 'Securities transaction tax is recorded and deducted nowhere: '
                                           + 'section 48 allows no deduction for it in computing a capital gain.' },
                            `STT ${rupees(c.stt)} not deducted`) : null),
             p ? el('td', { class: 'num' }, el('span', { class: 'why', style: 'color:var(--err)', title: p.needs.join('; ') }, 'rate needed'))
               : el('td', { class: 'num' }, c ? rupees(c.gain) : '—'),
             el('td', { class: 'term', title: c?.term_reason || '' },
                c ? `${c.term === 'long' ? 'Long' : 'Short'}-term` : '—',
                c ? el('span', { class: 'why' }, c.section === 'slab' ? 'slab rate' : `sec ${c.section}`) : null));
        })
      )),
      '',
      el('span', { class: 'src' },
         'Gain is sell value, less the cost used, less the expenses of the sale. Charges paid on '
         + 'purchase are part of the cost; securities transaction tax is deducted nowhere.')
    )
  );
  return out;
}


/* ------------------------------------------- schema-driven schedule layout */

/** Renders a schedule from its JSON Schema.
 *
 * The schemas carry each field's ITR item number in its `description`
 * ("Item 1(d)", "Column 11", "Table B(iv)(a)"), so the form layout is defined
 * once, in the schema, and drawn from it. That is what keeps sixteen schedules
 * looking like the ITR form without sixteen hand-written renderers, and it
 * means adding a field to a schedule is a schema edit, not a UI edit.
 *
 * Hand-written renderers still win where one exists (RENDERERS below); this is
 * the default for everything else.
 */

const ITEM_RE = /^(Item|Column|Table)\s+([^\s,.]+)/i;

function itemLabel(description) {
  const m = ITEM_RE.exec(description || '');
  return m ? m[2].replace(/[,.]$/, '') : '';
}

function prettyKey(key) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b(\d+[a-z]*)\b/gi, (x) => x)
    .replace(/^./, (c) => c.toUpperCase());
}

const isMoney = (schema) =>
  schema && (schema.$ref === '#/$defs/money' ||
             (schema.properties && schema.properties.amount));

function schemaRows(dataSchema, data, pointer, out) {
  const props = dataSchema.properties || {};
  for (const [key, sub] of Object.entries(props)) {
    const value = data ? data[key] : undefined;
    const here = `${pointer}/${key}`;
    const code = itemLabel(sub.description);
    const name = prettyKey(key);

    if (isMoney(sub)) {
      out.push(el('tr', {}, label(code, name), money(value, `${here}/amount`)));
    } else if (sub.type === 'array') {
      const rows = Array.isArray(value) ? value : [];
      out.push(el('tr', { class: 'sub' },
        label(code, `${name} — ${rows.length} row(s)`),
        el('td', { class: 'num' }, rows.length ? '' : '—')));
      rows.forEach((row, i) => {
        const inner = [];
        schemaRows(sub.items || {}, row, `${here}/${i}`, inner);
        out.push(...inner);
      });
    } else if (sub.type === 'object' || sub.properties) {
      out.push(el('tr', { class: 'sub' }, label(code, name), el('td', {}, '')));
      schemaRows(sub, value || {}, here, out);
    } else if (value !== undefined && value !== null && value !== '') {
      out.push(el('tr', {}, label(code, name), el('td', { class: 'num' }, String(value))));
    }
  }
}

function renderFromSchema(d, schema) {
  const dataSchema = schema?.properties?.data;
  if (!dataSchema) return renderGeneric(d);

  const rows = [];
  schemaRows(dataSchema, d.data || {}, '/data', rows);
  return [
    card(
      schema.title || 'Schedule',
      table(['ITR item', { t: 'Amount', num: true }], rows),
      '',
      el('span', { class: 'src' }, 'laid out from the schedule schema')
    ),
  ];
}


/** Schedule BP: the bridge from what the books say to what the Act taxes. */
function renderBusiness(d) {
  // Its own document once computed; the summary's copy is the fallback for a
  // page loaded before the first recompute.
  const b = d?.data?.rows ? d.data : computedHead('business');
  if (!b) {
    return [card('Nothing to compute yet',
      el('div', { class: 'card-body empty' },
         'Schedule BP is computed from Books and Depreciation. Read Books first.'))];
  }

  const out = [];
  if (b.warnings?.length) {
    out.push(card(`Before you rely on this (${b.warnings.length})`,
      el('div', { class: 'card-body' },
         el('ul', { class: 'plain' }, b.warnings.map((w) => el('li', {}, w)))), 'warn'));
  }

  out.push(card('Schedule BP',
    table(['Item', { t: 'Amount ₹', num: true }],
      b.rows.map((r) => el('tr', { class: r.kind === 'total' ? 'total' : r.kind === 'sub' ? 'sub' : '' },
        el('td', {}, el('span', { class: 'item-label' }, r.item), r.label,
           r.note ? el('span', { class: 'why' }, r.note) : null),
        el('td', { class: 'num' + (r.amount < 0 ? ' neg' : '') }, rupees(r.amount))))),
    '', el('span', { class: 'src' }, b.verify)));

  // Section 32, asset by asset and year by year. A single "depreciation"
  // figure is the least checkable number in a return: it depends on a date,
  // a rate and every year since the asset was bought, none of which appear
  // anywhere else.
  const sd = b.depreciation_schedule || {};
  if (sd?.assets?.length) {
    const rows = [];
    const trunks = sd.assets.map((asset) => {
      const head = el('tr', { class: 'itemrow' },
        el('td', {},
           el('span', { class: 'item-label' }, asset.schedule.replace('Schedule ', '')),
           asset.description,
           el('span', { class: 'why' },
              `${asset.block_label} at ${asset.rate_percent}% \u00b7 cost `
              + `${rupees(asset.cost)} \u00b7 put to use ${asset.put_to_use_on} `
              + `(${asset.acquired_in})`)),
        el('td', { class: 'num' }, rupees(asset.depreciation)));
      const kids = asset.working.map((r) => branch(el('tr', { class: 'sub' },
        el('td', {},
           el('span', { class: 'payer' }, `FY ${r.fy}`),
           el('span', { class: 'why' },
              `opening ${rupees(r.opening)} at ${(r.rate * 100).toFixed(0)}%`
              + (r.half_year
                   ? ` \u2014 half the ${(r.full_rate * 100).toFixed(0)}% rate, because it was `
                     + `in use ${r.days_in_use} days, under 180, in the year it was bought `
                     + '(second proviso to section 32(1))'
                   : '')
              + ` \u2192 closing ${rupees(r.closing)}`)),
        el('td', { class: 'num' }, rupees(r.depreciation)))));
      return branch(head, kids);
    });
    trunks.forEach((t) => rows.push(...t.rows));
    rows.push(el('tr', { class: 'total' },
      el('td', {}, `Depreciation allowable for ${sd.previous_year}, to Schedule BP item A12`),
      el('td', { class: 'num' }, rupees(sd.total_depreciation))));

    const openAll = el('button', { class: 'linkish', onclick: () => {
      const opening = openAll.dataset.open !== 'yes';
      trunks.forEach((t) => (opening ? t.openDeep() : t.close()));
      openAll.dataset.open = opening ? 'yes' : 'no';
      openAll.textContent = opening ? 'Collapse all' : 'Expand all';
    }, 'data-open': 'no' }, 'Expand all');

    out.push(card('Depreciation under section 32',
      table(['Asset', { t: 'This year', num: true }], rows), '',
      el('span', { class: 'asides' }, openAll, el('span', { class: 'src' }, sd.verify))));

    if (sd.ignored?.length) {
      out.push(card(`${sd.ignored.length} item(s) could not be depreciated`,
        el('div', { class: 'card-body' },
          el('ul', { class: 'plain' }, sd.ignored.map((x) =>
            el('li', {}, x.description, el('span', { class: 'why' }, x.why))))), 'warn'));
    }
  }

  if (b.derivatives_note) {
    out.push(card('Check this before filing',
      el('div', { class: 'card-body' }, el('p', { style: 'margin:0' }, b.derivatives_note)), 'warn'));
  }

  // What the business actually cost to run. A broker's profit is gross of
  // these, so they are the difference between tax on what you earned and tax
  // on what you turned over -- and section 32 relief belongs in the same
  // answer, because a monitor bought for the business is a cost of running it
  // even though the Act spreads it over years rather than allowing it at once.
  const ch = b.charges || {};
  const segments = [
    ['Futures and options', ch.derivatives || [], 'broker charges on the F&O business'],
    ['Intraday (speculative)', ch.speculative || [], 'broker charges on intraday trades'],
  ].filter(([, list]) => list.length);

  const costRows = [];
  const costTrunks = [];
  const pushGroup = (heading, caption, total, kids) => {
    const headRow = el('tr', { class: 'itemrow' },
      el('td', {}, heading, caption ? el('span', { class: 'why' }, caption) : null),
      el('td', { class: 'num' }, rupees(total)));
    const trunk = branch(headRow, kids);
    costTrunks.push(trunk);
    costRows.push(...trunk.rows);
  };

  segments.forEach(([heading, list, caption]) => {
    pushGroup(heading, `${list.length} head(s) \u00b7 ${caption}`,
      list.reduce((t, c) => t + c.amount, 0),
      list.map((c) => branch(el('tr', { class: 'sub' },
        el('td', {}, c.head, c.note ? el('span', { class: 'why' }, c.note) : null),
        el('td', { class: 'num' }, rupees(c.amount))))));
  });

  // Costs tied to no one segment are grouped by the document they came from,
  // because "did my invoices actually get used?" is the question being asked
  // and a single bucket of forty-nine rows cannot answer it.
  const loose = ch.other || [];
  if (loose.length) {
    const bySource = new Map();
    loose.forEach((c) => {
      // Group by the document that was supplied, not by each file inside it:
      // twelve monthly bills in one archive are one piece of evidence, and
      // twelve groups of one item answer nothing.
      const key = (c.source || '(source not stated)').split('/')[0];
      if (!bySource.has(key)) bySource.set(key, []);
      bySource.get(key).push(c);
    });
    const kids = [...bySource.entries()]
      .sort((x, y) => y[1].reduce((t, c) => t + c.amount, 0)
                    - x[1].reduce((t, c) => t + c.amount, 0))
      .map(([source, list]) => branch(
        el('tr', { class: 'sub' },
          el('td', {}, el('span', { class: 'payer' }, source),
             el('span', { class: 'why' }, `${list.length} item(s)`)),
          el('td', { class: 'num' }, rupees(list.reduce((t, c) => t + c.amount, 0)))),
        list.map((c) => branch(el('tr', { class: 'sub2' },
          el('td', {}, c.head, c.note ? el('span', { class: 'why' }, c.note) : null),
          el('td', { class: 'num' }, rupees(c.amount)))))));
    pushGroup('Running costs, not tied to one segment',
      `${loose.length} item(s) across ${bySource.size} document(s)`,
      loose.reduce((t, c) => t + c.amount, 0), kids);
  }

  if (sd.assets?.length) {
    pushGroup('Assets, relieved through depreciation',
      `${sd.assets.length} asset(s) \u00b7 section 32, this year's share of the cost`,
      sd.total_depreciation,
      sd.assets.map((asset) => branch(el('tr', { class: 'sub' },
        el('td', {}, el('span', { class: 'payer' }, asset.description),
           el('span', { class: 'why' },
              `cost ${rupees(asset.cost)} in ${asset.acquired_in}, written down at `
              + `${asset.rate_percent}% \u00b7 ${rupees(asset.opening_wdv || asset.cost)} `
              + `brought into this year, ${rupees(asset.closing_wdv)} carried out`)),
        el('td', { class: 'num' }, rupees(asset.depreciation))))));
  }

  if (costRows.length) {
    costRows.push(el('tr', {}, el('td', {}, 'Charges and running costs'),
      el('td', { class: 'num' }, rupees(ch.total || 0))));
    if (sd.total_depreciation) {
      costRows.push(el('tr', {}, el('td', {}, 'Depreciation allowed under section 32'),
        el('td', { class: 'num' }, rupees(sd.total_depreciation))));
    }
    costRows.push(el('tr', { class: 'total' },
      el('td', {}, 'What the business cost to run'),
      el('td', { class: 'num' }, rupees((ch.total || 0) + (sd.total_depreciation || 0)))));

    const openCosts = el('button', { class: 'linkish', onclick: () => {
      const opening = openCosts.dataset.open !== 'yes';
      costTrunks.forEach((t) => (opening ? t.openDeep() : t.close()));
      openCosts.dataset.open = opening ? 'yes' : 'no';
      openCosts.textContent = opening ? 'Collapse all' : 'Expand all';
    }, 'data-open': 'no' }, 'Expand all');

    out.push(card('What the business cost to run',
      table(['Cost', { t: 'Amount \u20b9', num: true }], costRows), '',
      el('span', { class: 'asides' }, openCosts,
         el('span', { class: 'src' },
            'brokerage, exchange and clearing charges, STT, stamp duty, SEBI fees and GST, '
            + 'the bills and invoices for the year, and section 32 relief on assets \u2014 '
            + 'every one of them deductible against business income'))));
  }

  const dep = b.depreciation || {};
  if (dep.books) out.push(card('Depreciation: books against the Act',
    table(['', { t: 'Amount ₹', num: true }],
      [el('tr', {}, el('td', {}, 'Charged in the books, added back'), el('td', { class: 'num' }, rupees(dep.books))),
       el('tr', {}, el('td', {}, `Allowable under section 32${dep.blocks ? ` (${dep.blocks} block(s))` : ''}`),
          el('td', { class: 'num' }, rupees(-dep.act))),
       el('tr', { class: 'total' }, el('td', {}, 'Net effect on business income'),
          el('td', { class: 'num' }, rupees(dep.books - dep.act)))]),
    '', el('span', { class: 'src' }, 'the books have their own view of depreciation; only the Act’s counts')));

  return out;
}

// Schedule FA prints its sections with these headings and in this order. A
// section with nothing in it is still shown, because "no foreign trusts" and
// "we did not look for foreign trusts" are different statements and only one
// of them is safe under the Black Money Act.
const FA_SECTIONS = [
  ['a1_depository_accounts', 'A1', 'Foreign Depository Accounts held', 'account'],
  ['a2_custodial_accounts', 'A2', 'Foreign Custodial Accounts held', 'account'],
  ['a3_equity_and_debt', 'A3', 'Foreign Equity and Debt interest held in any entity', 'equity'],
  ['a4_insurance_contracts', 'A4', 'Foreign Cash Value Insurance or Annuity Contract held', 'other'],
  ['b_financial_interest', 'B', 'Financial Interest in any Entity held', 'other'],
  ['c_immovable_property', 'C', 'Immovable Property held', 'other'],
  ['d_other_capital_assets', 'D', 'Any other Capital Asset held', 'other'],
  ['e_signing_authority', 'E', 'Accounts in which you have signing authority', 'other'],
  ['f_trusts', 'F', 'Trusts created outside India', 'other'],
  ['g_other_income', 'G', 'Any other income derived from a source outside India', 'other'],
];

const FSI_HEADS = [['i', 'Salary'], ['ii', 'House Property'],
                   ['iii', 'Business or Profession'], ['iv', 'Capital Gains'],
                   ['v', 'Other Sources']];

const amt = (node) => (node && typeof node === 'object' ? node.amount : node) || 0;

/** Schedules FSI, TR and FA, laid out the way the return prints them. */
function renderForeign(d) {
  const data = d?.data || {};
  const out = [];
  // Schedules FSI and TR are computed from the receipts, not transcribed:
  // column (c) is the foreign income already inside Part B-TI after Rule 115,
  // and no document states that. The extraction's own copy is the fallback for
  // a page opened before the first recompute.
  const computed = computedRegime()?.foreign || null;

  // ---- Schedule FSI --------------------------------------------------
  const fsi = computed?.schedule_fsi || data.schedule_fsi || [];
  if (fsi.length) {
    const rows = [];
    const trunks = [];
    let total = { c: 0, dd: 0, e: 0, f: 0 };
    fsi.forEach((country, i) => {
      const byItem = new Map((country.heads || []).map((h) => [String(h.item), h]));
      const heads = FSI_HEADS.map(([item, name]) => byItem.get(item)
        || { item, head: name, income_outside_india: { amount: 0 } });
      const sums = heads.reduce((a, h) => ({
        c: a.c + amt(h.income_outside_india), dd: a.dd + amt(h.tax_paid_outside_india),
        e: a.e + amt(h.tax_payable_in_india), f: a.f + amt(h.relief_available),
      }), { c: 0, dd: 0, e: 0, f: 0 });
      total = { c: total.c + sums.c, dd: total.dd + sums.dd,
                e: total.e + sums.e, f: total.f + sums.f };

      const head = el('tr', { class: 'itemrow' },
        el('td', {}, el('span', { class: 'item-label' }, String(i + 1)),
           `${country.country_code} - ${country.country}`,
           el('span', { class: 'why' },
              country.taxpayer_identification_number
                ? `Taxpayer Identification Number ${country.taxpayer_identification_number}`
                : 'no taxpayer identification number stated')),
        el('td', { class: 'num' }, rupees(sums.c)),
        el('td', { class: 'num' }, rupees(sums.dd)),
        el('td', { class: 'num' }, rupees(sums.e)),
        el('td', { class: 'num' }, rupees(sums.f)),
        el('td', {}, ''));
      const kids = heads.map((h) => branch(el('tr', { class: 'sub' },
        el('td', {}, el('span', { class: 'item-label' }, h.item), h.head),
        el('td', { class: 'num' }, rupees(amt(h.income_outside_india))),
        el('td', { class: 'num' }, rupees(amt(h.tax_paid_outside_india))),
        el('td', { class: 'num' }, rupees(amt(h.tax_payable_in_india))),
        el('td', { class: 'num' }, rupees(amt(h.relief_available))),
        el('td', { class: 'src' }, h.dtaa_article ? `Article ${h.dtaa_article}` : ''))));
      const trunk = branch(head, kids);
      trunks.push(trunk);
      rows.push(...trunk.rows);
      trunk.show();
    });
    rows.push(el('tr', { class: 'total' }, el('td', {}, 'Total'),
      el('td', { class: 'num' }, rupees(total.c)), el('td', { class: 'num' }, rupees(total.dd)),
      el('td', { class: 'num' }, rupees(total.e)), el('td', { class: 'num' }, rupees(total.f)),
      el('td', {}, '')));

    out.push(card('Schedule FSI — Details of Income from outside India and tax relief',
      table([
        'Country and head of income',
        { t: '(c) Income from outside India', num: true },
        { t: '(d) Tax paid outside India', num: true },
        { t: '(e) Tax payable in India', num: true },
        { t: '(f) Relief available', num: true },
        'Article'], rows),
      '',
      el('span', { class: 'src' },
         (computed ? 'Computed from each receipt, converted at its own Rule 115 date. '
                   : 'As transcribed. ')
         + 'Available only to a resident. Column (c) is the income already included in '
         + 'Part B-TI; (f) is the lower of (d) and (e), under section 90(2).')));
    if (computed?.notes?.length) {
      out.push(card('About this relief',
        el('div', { class: 'card-body' },
          el('ul', { class: 'plain' }, computed.notes.map((n) => el('li', {}, n)))),
        computed.total_relief ? '' : 'warn'));
    }
  }

  // ---- Schedule TR ---------------------------------------------------
  const tr = computed?.schedule_tr || data.schedule_tr || {};
  const countries = tr.countries || [];
  if (countries.length) {
    const rows = countries.map((c, i) => el('tr', {},
      el('td', {}, el('span', { class: 'item-label' }, String(i + 1)),
         `${c.country_code} - ${c.country}`,
         c.taxpayer_identification_number
           ? el('span', { class: 'why' }, c.taxpayer_identification_number) : null),
      el('td', { class: 'num' }, rupees(amt(c.total_taxes_paid_outside))),
      el('td', { class: 'num' }, rupees(amt(c.total_relief_available))),
      el('td', {}, c.relief_section ? `Section ${c.relief_section}` : '—')));
    const paid = countries.reduce((a, c) => a + amt(c.total_taxes_paid_outside), 0);
    const relief = countries.reduce((a, c) => a + amt(c.total_relief_available), 0);
    rows.push(el('tr', { class: 'total' }, el('td', {}, 'Total'),
      el('td', { class: 'num' }, rupees(paid)), el('td', { class: 'num' }, rupees(relief)),
      el('td', {}, '')));
    const treaty = countries.filter((c) => String(c.relief_section || '').startsWith('90'))
      .reduce((a, c) => a + amt(c.total_relief_available), 0);
    rows.push(el('tr', {}, el('td', {}, el('span', { class: 'item-label' }, '2'),
      'Total tax relief available where DTAA is applicable (section 90 / 90A)'),
      el('td', { class: 'num' }, '—'), el('td', { class: 'num' }, rupees(treaty)),
      el('td', {}, '')));
    rows.push(el('tr', {}, el('td', {}, el('span', { class: 'item-label' }, '3'),
      'Total tax relief available where DTAA is not applicable (section 91)'),
      el('td', { class: 'num' }, '—'), el('td', { class: 'num' }, rupees(relief - treaty)),
      el('td', {}, '')));
    rows.push(el('tr', {}, el('td', {}, el('span', { class: 'item-label' }, '4a'),
      'Tax paid outside India, on which relief was allowed, later refunded by the foreign '
      + 'authority'),
      el('td', { class: 'num' }, '—'),
      el('td', { class: 'num' }, rupees(amt(tr.tax_refunded_by_foreign_authority))),
      el('td', {}, tr.refund_relates_to_ay ? `AY ${tr.refund_relates_to_ay}` : '')));

    out.push(card('Schedule TR — Summary of tax relief claimed for taxes paid outside India',
      table(['Country', { t: '(c) Total taxes paid outside India', num: true },
             { t: '(d) Total tax relief available', num: true }, '(e) Relief claimed under'],
            rows),
      '',
      el('span', { class: 'src' },
         'Relief under section 90, 90A or 91 requires Form 67 filed before the return.')));
  }

  // ---- Schedule FA ---------------------------------------------------
  // A1 to A3 are laid out with the form's own columns, from the computed
  // figures: every column is rupees at the rate for that figure's own date,
  // and each row opens to the working so the multiplication can be redone.
  const fa = data.schedule_fa || {};
  const faDone = computedRegime()?.foreign_assets || null;
  const year = faDone?.calendar_year || data.calendar_year || '(not stated)';
  const cell = (v) => el('td', { class: 'num' }, v === null || v === undefined ? '—' : rupees(v));
  const place = (x) => `${x.country_code ?? ''} - ${x.country ?? ''}`;
  const workingRows = (x, span) => {
    const lines = (x.steps || []).map((st) => {
      const k = st.working;
      return el('tr', { class: 'sub2' },
        el('td', { colspan: span },
           el('span', { class: 'src' }, st.on || 'no date'), ` ${st.label}`,
           k ? el('span', { class: 'fxwork' },
                  ` ${k.currency} ${Number(k.amount_foreign).toLocaleString('en-US')} x ${k.rate}`
                  + ` · SBI TT buy ${k.rate_date}`
                  + (k.rate_date !== k.date_wanted ? ` (for ${k.date_wanted})` : ''))
             : st.why ? el('span', { class: 'why' }, st.why) : null),
        cell(st.rupees));
    });
    (x.notes || []).forEach((n) => lines.push(el('tr', { class: 'sub2' },
      el('td', { colspan: span + 1, class: 'why' }, n))));
    return lines.map((r) => branch(r));
  };

  if (faDone?.error) {
    out.push(card('Schedule FA cannot be worked out yet',
      el('div', { class: 'card-body' }, faDone.error), 'warn'));
  }

  const faTrunks = [];
  const accountTable = (key, code, title) => {
    const items = faDone?.[key] || [];
    if (!items.length) return;
    const rows = [];
    items.forEach((x, i) => {
      const head = el('tr', {},
        el('td', {}, el('span', { class: 'item-label' }, String(i + 1)), place(x)),
        el('td', {}, x.institution_name || '—',
           el('span', { class: 'why' },
              [x.institution_address, x.zip_code].filter(Boolean).join(' · '))),
        el('td', {}, x.account_number || '—'),
        el('td', {}, x.status || '—'),
        el('td', { class: 'src' }, x.opened_on || '—'),
        cell(x.peak_value), cell(x.closing_value),
        el('td', {}, (x.credited || []).length
          ? x.credited.map((k) => el('div', {}, k.nature)) : '—'),
        el('td', { class: 'num' }, (x.credited || []).length
          ? x.credited.map((k) => el('div', {}, rupees(k.amount))) : '—'));
      const trunk = branch(head, workingRows(x, 8));
      faTrunks.push(trunk);
      rows.push(...trunk.rows);
    });
    out.push(card(`Schedule FA — ${code} ${title}`,
      table(['(2)(3) Country', '(4)(5)(6) Financial institution', '(7) Account number',
             '(8) Status', '(9) Opened',
             { t: '(10) Peak balance', num: true }, { t: '(11) Closing balance', num: true },
             '(12a) Nature', { t: '(12b) Amount', num: true }], rows),
      '', el('span', { class: 'src' }, `calendar year ${year}`)));
  };
  accountTable('a1_depository_accounts', 'A1', 'Foreign Depository Accounts');
  accountTable('a2_custodial_accounts', 'A2', 'Foreign Custodial Accounts');

  const holdings = faDone?.a3_equity_and_debt || [];
  if (holdings.length) {
    const rows = [];
    let serial = 0;
    // The form's rows are the acquisitions. A company with several is shown
    // under one heading that opens to them, so sixteen vests do not bury the
    // three holdings below.
    const lotRow = (x, lot, cls) => el('tr', { class: cls },
      el('td', {}, el('span', { class: 'item-label' }, String(++serial)), place(x)),
      el('td', {}, x.entity_name || '—',
         el('span', { class: 'why' },
            [lot.quantity ? `${lot.quantity} shares` : null, x.entity_address, x.zip_code]
              .filter(Boolean).join(' · '))),
      el('td', {}, x.nature_of_entity || '—'),
      el('td', { class: 'src' }, lot.acquired_on || '—'),
      cell(lot.initial_value), cell(lot.peak_value), cell(lot.closing_value),
      cell(lot.gross_amount_credited), cell(lot.gross_proceeds_on_sale));

    holdings.forEach((x) => {
      const lots = x.lots || [];
      if (lots.length === 1) {
        const trunk = branch(lotRow(x, lots[0], ''),
                             workingRows({ steps: lots[0].steps, notes: x.notes }, 8));
        faTrunks.push(trunk);
        rows.push(...trunk.rows);
        return;
      }
      const t = x.totals || {};
      const head = el('tr', { class: 'itemrow' },
        el('td', {}, place(x)),
        el('td', {}, x.entity_name || '—',
           el('span', { class: 'why' }, `${lots.length} acquisitions, one row each`)),
        el('td', {}, x.nature_of_entity || '—'), el('td', {}, ''),
        cell(t.initial_value), el('td', { class: 'num' }, ''), cell(t.closing_value),
        cell(t.gross_amount_credited), cell(t.gross_proceeds_on_sale));
      const kids = lots.map((lot) => branch(lotRow(x, lot, 'sub'),
                                            workingRows({ steps: lot.steps, notes: [] }, 8)));
      (x.notes || []).forEach((n) => kids.push(branch(el('tr', { class: 'sub2' },
        el('td', { colspan: 9, class: 'why' }, n)))));
      const trunk = branch(head, kids);
      faTrunks.push(trunk);
      rows.push(...trunk.rows);
      trunk.show();
    });
    out.push(card('Schedule FA — A3 Foreign Equity and Debt Interest',
      table(['(2)(3) Country', '(4)(5)(6) Entity', '(7) Nature', '(8) Date acquired',
             { t: '(9) Initial value', num: true }, { t: '(10) Peak value', num: true },
             { t: '(11) Closing value', num: true },
             { t: '(12) Gross amount credited', num: true },
             { t: '(13) Gross sale proceeds', num: true }], rows),
      '', el('span', { class: 'src' }, faDone.verify)));
  }

  if (faDone?.rates_needed?.length) {
    out.push(card(`${faDone.rates_needed.length} rate(s) still needed for Schedule FA`,
      el('div', { class: 'card-body' },
        el('p', { style: 'margin:0 0 8px' },
           'Figures on these dates are left out until the SBI TT buying rate is known:'),
        el('p', { class: 'src', style: 'margin:0' },
           faDone.rates_needed.map((n) => `${n.currency} ${n.date}`).join(' · '))), 'warn'));
  }

  // The remaining sections, in the form's order. An empty one is shown,
  // because "none held" has to be a statement and not an absence.
  const others = FA_SECTIONS.filter(([key]) => !['a1_depository_accounts',
    'a2_custodial_accounts', 'a3_equity_and_debt'].includes(key) || !(faDone?.[key] || []).length);
  if (Object.keys(fa).length || faDone) {
    const rows = others.map(([key, code, title]) => {
      const n = (fa[key] || []).length;
      return el('tr', { class: n ? '' : 'skip' },
        el('td', {}, el('span', { class: 'item-label' }, code), title),
        el('td', {}, n ? `${n} item(s) reported` : 'nothing reported'));
    });
    out.push(card('Schedule FA — other sections',
      table(['Section', 'Reported'], rows), '',
      el('span', { class: 'src' },
         `Calendar year ${year}, 1 January to 31 December, not the previous year.`)));
  }

  if (!out.length) {
    out.push(card('Nothing read yet',
      el('div', { class: 'card-body empty' },
         'Schedules FSI, TR and FA are built from foreign broker statements, Form 1042-S '
         + 'and foreign bank statements. Read this schedule once those are among the documents.')));
  }
  return out;
}

/* ------------------------------------------------- depreciation schedules */

const DPM_RATES = [15, 30, 40, 45];
const DOA_COLUMNS = [
  ['Land', 'nil', null], ['Building', '5', null], ['Building', '10', 'building'],
  ['Building', '40', null], ['Furniture and fittings', '10', 'furniture'],
  ['Intangible assets', '25', 'intangible'], ['Ships', '20', null],
];

/** The lines Schedules DPM and DOA print for one block. */
function depreciationLines(b) {
  const z = (v) => v || 0;
  if (!b) return null;
  const full = z(b.opening_wdv) + z(b.additions_180_days_or_more);
  const half = z(b.additions_less_than_180_days);
  return {
    '3a': z(b.opening_wdv), '3b': 0, 3: z(b.opening_wdv),
    4: z(b.additions_180_days_or_more), 5: 0, 6: full,
    7: half, 8: 0, 9: half,
    10: z(b.depreciation_full_rate), 11: z(b.depreciation_half_rate),
    12: 0, 13: 0, 14: 0, 15: z(b.depreciation_allowable), 16: 0,
    17: z(b.depreciation_allowable), 19: 0, 20: 0, 21: z(b.closing_wdv),
  };
}

const DEP_LINE_LABELS = [
  ['3a', 'Written down value on the first day of previous year'],
  ['3b', 'Adjustment as per second proviso to sub-section 3 of section 115BAC'],
  ['3', 'Total (3a + 3b)'],
  ['4', 'Additions for a period of 180 days or more in the previous year'],
  ['5', 'Consideration or other realizations during the year out of 3 or 4'],
  ['6', 'Amount on which depreciation at full rate to be allowed (3 + 4 - 5)'],
  ['7', 'Addition for a period of less than 180 days in the previous year'],
  ['8', 'Consideration or other realizations during the year out of 7'],
  ['9', 'Amount on which depreciation at half rate to be allowed (7 - 8)'],
  ['10', 'Depreciation on 6 at full rate'],
  ['11', 'Depreciation on 9 at half rate'],
  ['12', 'Additional depreciation, if any, on 4'],
  ['13', 'Additional depreciation, if any, on 7'],
  ['14', 'Additional depreciation relating to immediately preceding year on asset put to use for less than 180 days'],
  ['15', 'Total depreciation (10 + 11 + 12 + 13 + 14)'],
  ['16', 'Depreciation disallowed under section 38(2) of the I.T. Act (out of column 15)'],
  ['17', 'Net aggregate depreciation (15 - 16)'],
  ['19', 'Expenditure incurred in connection with transfer of asset/assets'],
  ['20', 'Capital gains / loss under section 50 (5 + 8 - 3 - 4 - 7 - 19)'],
  ['21', 'Written down value on the last day of previous year (6 + 9 - 15)'],
];

function renderDepreciation(d) {
  const sd = d?.data || {};
  const blocks = sd.blocks || [];
  const out = [];
  if (!blocks.length) {
    return [card('No depreciable assets',
      el('div', { class: 'card-body empty' },
         'No asset has been found on any invoice, so Schedules DPM, DOA and DEP are nil. '
         + 'An asset bought for the business is picked up from its invoice when Books is read.'))];
  }

  const scheduleTable = (title, columns, pick) => {
    const lines = columns.map((col) => depreciationLines(pick(col)));
    if (!lines.some(Boolean)) return;
    const rows = DEP_LINE_LABELS.map(([no, text]) => el('tr',
      { class: ['3', '15', '17', '21'].includes(no) ? 'total' : '' },
      el('td', {}, el('span', { class: 'item-label' }, no), text),
      lines.map((l) => el('td', { class: 'num' }, l ? rupees(l[no]) : rupees(0)))));
    out.push(card(title,
      table(['1  Block of assets / 2  Rate',
             ...columns.map((col) => ({ t: col.heading, num: true }))], rows)));
  };

  scheduleTable('Schedule DPM — Depreciation on Plant and Machinery',
    DPM_RATES.map((r, i) => ({ heading: `${r}% (${['i', 'ii', 'iii', 'iv'][i]})`, rate: r })),
    (col) => blocks.find((b) => b.schedule === 'Schedule DPM' && Number(b.rate_percent) === col.rate));
  scheduleTable('Schedule DOA — Depreciation on Other Assets',
    DOA_COLUMNS.map(([name, rate, key], i) => ({
      heading: `${name} ${rate}${rate === 'nil' ? '' : '%'} (${['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii'][i]})`, key })),
    (col) => (col.key ? blocks.find((b) => b.schedule === 'Schedule DOA' && b.block === col.key) : null));

  // Schedule DEP: the same figures, gathered by kind of asset.
  const dpm = (r) => blocks.filter((b) => b.schedule === 'Schedule DPM' && Number(b.rate_percent) === r)
    .reduce((a, b) => a + (b.depreciation_allowable || 0), 0);
  const doa = (key) => blocks.filter((b) => b.schedule === 'Schedule DOA' && b.block === key)
    .reduce((a, b) => a + (b.depreciation_allowable || 0), 0);
  const plant = DPM_RATES.reduce((a, r) => a + dpm(r), 0);
  const line = (no, text, v, cls = '') => el('tr', { class: cls },
    el('td', {}, el('span', { class: 'item-label' }, no), text),
    el('td', { class: 'num' }, rupees(v)));
  out.push(card('Schedule DEP — Summary of depreciation on assets',
    table(['Item', { t: 'Amount', num: true }], [
      line('1a', 'Plant and machinery: block entitled for depreciation @ 15 percent', dpm(15)),
      line('1b', 'Plant and machinery: block entitled for depreciation @ 30 percent', dpm(30)),
      line('1c', 'Plant and machinery: block entitled for depreciation @ 40 percent', dpm(40)),
      line('1d', 'Plant and machinery: block entitled for depreciation @ 45 percent', dpm(45)),
      line('1e', 'Total depreciation on plant and machinery (1a + 1b + 1c + 1d)', plant, 'total'),
      line('2', 'Building (not including land)', doa('building')),
      line('3', 'Furniture and fittings', doa('furniture')),
      line('4', 'Intangible assets', doa('intangible')),
      line('5', 'Ships', 0),
      line('6', 'Total depreciation (1e + 2 + 3 + 4 + 5)', sd.total_depreciation || 0, 'total'),
    ]),
    '', el('span', { class: 'src' },
           'Carried to Schedule BP as the depreciation allowable under section 32. Item numbers '
           + 'within 2 to 6 follow the form\u2019s pattern; check them against the utility.')));

  // Asset by asset, year by year: the working the blocks are built from.
  const rows = [];
  const trunks = (sd.assets || []).map((asset) => {
    const head = el('tr', { class: 'itemrow' },
      el('td', {}, asset.description,
         el('span', { class: 'why' },
            `${asset.block_label} at ${asset.rate_percent}% \u00b7 cost ${rupees(asset.cost)} `
            + `\u00b7 put to use ${asset.put_to_use_on} (${asset.acquired_in})`)),
      el('td', { class: 'num' }, rupees(asset.opening_wdv || asset.addition_this_year)),
      el('td', { class: 'num' }, rupees(asset.depreciation)),
      el('td', { class: 'num' }, rupees(asset.closing_wdv)));
    const kids = (asset.working || []).map((r) => branch(el('tr', { class: 'sub' },
      el('td', {}, el('span', { class: 'payer' }, `FY ${r.fy}`),
         el('span', { class: 'why' },
            `${(r.rate * 100).toFixed(0)}%`
            + (r.half_year ? ` \u2014 half the ${(r.full_rate * 100).toFixed(0)}% rate: in use `
                             + `${r.days_in_use} days, under 180, in the year it was bought` : ''))),
      el('td', { class: 'num' }, rupees(r.opening)),
      el('td', { class: 'num' }, rupees(r.depreciation)),
      el('td', { class: 'num' }, rupees(r.closing)))));
    return branch(head, kids);
  });
  trunks.forEach((t) => rows.push(...t.rows));
  if (rows.length) {
    out.push(card('The assets behind the blocks',
      table(['Asset', { t: 'Opening value this year', num: true },
             { t: 'Depreciation this year', num: true }, { t: 'Closing value', num: true }], rows),
      '', el('span', { class: 'src' }, sd.verify || '')));
  }
  out.push(card('Schedule DCG — Deemed capital gain on sale of depreciable assets',
    el('div', { class: 'card-body' },
       'Nil. No depreciable asset was sold or discarded during the year, so no block gives '
       + 'rise to a gain under section 50.')));
  return out;
}

/* ------------------------------------------- set-off and carry forward */

const LOSS_KINDS = {
  house_property: 'House property loss',
  business_non_speculative: 'Business loss (other than speculative and specified)',
  business_speculative: 'Speculative business loss',
  specified_business_35AD: 'Specified business loss',
  short_term_capital: 'Short-term capital loss',
  long_term_capital: 'Long-term capital loss',
  other_sources_race_horses: 'Loss from race horses',
  unabsorbed_depreciation: 'Unabsorbed depreciation',
};

function renderSetoff(d) {
  const out = [];
  const so = computedRegime()?.cascade?.setoff;
  const supplied = d?.data?.brought_forward || [];
  const num = (v) => el('td', { class: 'num' }, rupees(v || 0));

  out.push(card('Losses brought forward from earlier years, as supplied',
    supplied.length
      ? table(['Assessment year', 'Kind of loss', { t: 'Amount', num: true }],
          supplied.map((x, i) => el('tr', {},
            el('td', {}, x.ay_of_origin,
               x.return_filed_on ? el('span', { class: 'why' }, `return filed ${x.return_filed_on}`) : null),
            el('td', {}, LOSS_KINDS[x.kind] || x.kind),
            money(x.amount, `/data/brought_forward/${i}/amount/amount`))))
      : el('div', { class: 'card-body' },
          'None supplied, so every brought-forward line below is nil. If you carried a loss '
          + 'into this year, add last year\u2019s return or its intimation under section 143(1) '
          + 'to the documents folder, sort the documents again on the Documents page, then read '
          + 'this schedule. Only that '
          + 'return\u2019s Schedule CFL is read.'),
    supplied.length ? '' : 'warn'));

  if (!so) {
    out.push(card('Not computed yet',
      el('div', { class: 'card-body empty' }, 'Open Computation and press Recompute.')));
    return out;
  }

  // ---- Schedule CYLA
  const c = so.cyla;
  out.push(card('Schedule CYLA — Details of income after set off of current year losses',
    table(['Head / Source of income', { t: '(1) Income of current year', num: true },
           { t: '(2) House property loss set off', num: true },
           { t: '(3) Business loss set off', num: true },
           { t: '(4) Other sources loss set off', num: true },
           { t: '(5) Income remaining after set off', num: true }], [
      el('tr', {}, el('td', {}, el('span', { class: 'item-label' }, 'i'), 'Loss to be set off'),
         el('td', { class: 'num' }, ''), num(c.loss.hp_loss), num(c.loss.business_loss),
         num(c.loss.os_loss), el('td', { class: 'num' }, '')),
      ...c.rows.map((r) => el('tr', { class: r.income ? '' : 'skip' },
        el('td', {}, el('span', { class: 'item-label' }, r.no), r.label),
        num(r.income), num(r.hp_loss), num(r.business_loss), num(r.os_loss), num(r.remaining))),
      el('tr', { class: 'total' },
         el('td', {}, el('span', { class: 'item-label' }, 'xvi'), 'Total loss set off'),
         el('td', { class: 'num' }, ''), num(c.set_off.hp_loss), num(c.set_off.business_loss),
         num(c.set_off.os_loss), el('td', { class: 'num' }, '')),
      el('tr', {},
         el('td', {}, el('span', { class: 'item-label' }, 'xvii'), 'Loss remaining after set-off (i - xvi)'),
         el('td', { class: 'num' }, ''), num(c.remaining.hp_loss), num(c.remaining.business_loss),
         num(c.remaining.os_loss), el('td', { class: 'num' }, '')),
    ])));

  // ---- Schedule BFLA
  const b = so.bfla;
  out.push(card('Schedule BFLA — Details of income after set off of brought forward losses of earlier years',
    table(['Head / Source of income',
           { t: '(1) Income after set off of current year\u2019s losses (5 of Schedule CYLA)', num: true },
           { t: '(2) Brought forward loss set off', num: true },
           { t: '(3) Brought forward depreciation set off', num: true },
           { t: '(4) Brought forward allowance under section 35(4) set off', num: true },
           { t: '(5) Current year\u2019s income remaining after set off', num: true }], [
      ...b.rows.map((r) => el('tr', { class: r.income ? '' : 'skip' },
        el('td', {}, el('span', { class: 'item-label' }, r.no), r.label),
        num(r.income), num(r.bf_loss), num(r.bf_depreciation), num(r.bf_allowance_35_4),
        num(r.remaining))),
      el('tr', { class: 'total' },
         el('td', {}, el('span', { class: 'item-label' }, 'xv'), 'Total of brought forward loss set off'),
         el('td', { class: 'num' }, ''), num(b.rows.reduce((a, r) => a + r.bf_loss, 0)),
         num(b.rows.reduce((a, r) => a + r.bf_depreciation, 0)), num(0),
         el('td', { class: 'num' }, '')),
      el('tr', { class: 'total' },
         el('td', { colspan: 5 }, el('span', { class: 'item-label' }, 'xvi'),
            'Current year\u2019s income remaining after set off, total'),
         num(b.total_remaining)),
    ])));

  // ---- Schedule CFL
  const f = so.cfl;
  const cols = f.columns;
  const lossRow = (no, text, values, cls = '') => el('tr', { class: cls },
    el('td', {}, el('span', { class: 'item-label' }, no), text),
    cols.map((col) => num(values[col.key])));
  const roman = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii',
                 'xiii', 'xiv', 'xv', 'xvi'];
  out.push(card('Schedule CFL — Details of losses to be carried forward to future years',
    table(['Assessment year', ...cols.map((col) => ({ t: col.label, num: true }))], [
      ...f.rows.map((r, i) => lossRow(roman[i] || '', r.ay, r,
        cols.some((col) => r[col.key]) ? '' : 'skip')),
      lossRow('', 'Total of earlier year losses b/f', f.brought_forward, 'total'),
      lossRow('', 'Adjustment of above losses in Schedule BFLA', f.adjusted_in_bfla),
      lossRow('', 'Earlier losses that lapse after this year', f.lapsing),
      lossRow('', `${f.current_ay} (current year losses to be carried forward)`, f.current_year),
      lossRow('', 'Total loss carried forward to future years', f.carried_forward, 'total'),
    ]),
    '', el('span', { class: 'src' },
           'Row numbers for the totals depend on how many years the utility lists; the rows '
           + 'themselves are the form\u2019s.')));

  if (so.ud?.length) {
    out.push(card('Schedule UD — Unabsorbed depreciation',
      table(['Assessment year', { t: 'Brought forward', num: true },
             { t: 'Set off this year', num: true }, { t: 'Balance carried forward', num: true }],
        so.ud.map((r) => el('tr', {}, el('td', {}, r.ay), num(r.brought_forward),
                            num(r.set_off), num(r.balance))))));
  }

  if (so.notes?.length) {
    out.push(card('How each loss was treated',
      el('div', { class: 'card-body' },
        el('ul', { class: 'plain' }, so.notes.map((n) => el('li', {}, n))))));
  }
  return out;
}

/* ------------------------------------------------------------ Schedule 112A */

const S112A_ACQUIRED = {
  after: 'After 31st January 2018',
  on_or_before: 'On or before 31st January 2018',
  unknown: 'Date not known',
};

/** Schedule 112A in the form's own columns, 1 to 14.
 *
 * Built from the capital gains ledger, so it cannot differ from Schedule CG.
 * Sales of shares acquired after 31 January 2018 are one consolidated row, as
 * the form allows; the row opens to the sales it adds up, which is the evidence
 * for it. Earlier acquisitions are listed scrip by scrip, because their cost
 * may be replaced by the fair market value of that day. */
function renderSchedule112A(d) {
  const s = d?.data || {};
  const rows = s.rows || [];
  if (!rows.length) {
    return [card('Schedule 112A',
      el('div', { class: 'card-body empty' },
         'No long-term sale of listed equity shares or equity-oriented units on which STT was '
         + 'paid is in the Capital Gains ledger, so this schedule is nil.'))];
  }

  const columns = s.columns || [];
  const num = (v) => el('td', { class: 'num' }, typeof v === 'number' ? rupees(v) : '');
  const plain = (v) => el('td', { class: 'num' },
    v === null || v === undefined || v === '' ? ''
      : typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : String(v));

  const cellsFor = (r, lot) => [
    el('td', { class: 'ln' }, lot ? '' : String(r.sl ?? '')),
    // A sale under the consolidated row shows when it was bought and sold,
    // one date above the other, where the row itself says which side of the
    // day it falls on.
    lot ? el('td', { class: 'dates', title: 'acquired, then transferred' },
             el('span', {}, r.acquired_on || 'no date'), el('span', {}, r.transferred_on || ''))
        : el('td', {}, S112A_ACQUIRED[r.acquired] || ''),
    el('td', { class: 'src' }, r.isin || ''),
    el('td', { class: 'desc' }, r.name || '',
       !lot && r.lots?.length
         ? el('span', { class: 'why' }, `${r.lots.length} sale${r.lots.length === 1 ? '' : 's'} added together`)
         : null),
    plain(r.quantity), plain(r.sale_price_per_unit),
    num(r.full_value), num(r.cost_without_indexation), num(r.cost_of_acquisition),
    num(r.lower_of_6_and_11 || (lot || r.acquired === 'after' ? null : 0)),
    plain(r.fmv_per_unit), num(r.fmv_total || (lot || r.acquired === 'after' ? null : 0)),
    num(r.expenditure), num(r.total_deductions),
    el('td', { class: 'num' + (r.balance < 0 ? ' neg' : '') }, rupees(r.balance)),
  ];

  const body = [];
  const trunks = [];
  rows.forEach((r) => {
    const head = el('tr', { class: r.lots?.length ? 'itemrow' : '' }, ...cellsFor(r, false));
    const kids = (r.lots || []).map((lot) => branch(el('tr', { class: 'sub' }, ...cellsFor(lot, true))));
    const trunk = branch(head, kids);
    trunks.push(trunk);
    body.push(...trunk.rows);
  });

  const t = s.totals || {};
  body.push(el('tr', { class: 'total' },
    el('td', { colspan: '6' }, 'Total of each column'),
    num(t.full_value), num(t.cost_without_indexation), num(t.cost_of_acquisition),
    el('td', {}), el('td', {}), el('td', {}),
    num(t.expenditure), num(t.total_deductions), num(t.balance)));

  const openAll = el('button', { class: 'linkish', onclick: () => {
    const opening = openAll.dataset.open !== 'yes';
    trunks.forEach((x) => (opening ? x.openDeep() : x.close()));
    openAll.dataset.open = opening ? 'yes' : 'no';
    openAll.textContent = opening ? 'Hide the sales' : 'Show the sales';
  }, 'data-open': 'no' }, 'Show the sales');

  const out = [card(
    'Schedule 112A \u2014 From sale of equity share in a company or unit of equity oriented fund '
    + 'or unit of a business trust on which STT is paid under section 112A',
    el('div', { class: 's112a' },
      // The heading in the form's words without their conditions; the whole
      // of it is on hover, because fifteen full headings leave no room for
      // the figures under them.
      table(columns.map((c) => ({
        t: el('span', { title: c.label }, el('b', {}, `(${c.no})`), ` ${c.short || c.label}`),
        num: Boolean(c.money) || ['4', '5', '10'].includes(c.no),
      })), body)),
    '',
    el('span', { class: 'asides' },
       rows.some((r) => r.lots?.length) ? openAll : null,
       el('span', { class: 'src' },
          `${s.sales} sale${s.sales === 1 ? '' : 's'} \u00b7 balance ${rupees(t.balance)} carried to ${s.carried_to}`)))];

  if (s.notes?.length) {
    out.push(card('How this schedule is put together',
      el('div', { class: 'card-body' },
        el('ul', { class: 'plain' }, s.notes.map((n) => el('li', {}, n)))),
      '', el('span', { class: 'src' }, s.verify || '')));
  }
  return out;
}

/** Part A-GEN: who the return is for, their bank accounts, and the choices
 *  no document makes. Text, not amounts, so it is laid out as a record. */
function renderGeneral(d) {
  const data = d.data || {};
  const a = data.assessee || {};
  const filing = data.filing || {};
  const missing = () => el('span', { class: 'muted' }, 'not in the documents');
  const row = (label, value, mono) => el('tr', {},
    el('td', { style: 'width:220px;color:var(--muted)' }, label),
    el('td', { class: mono && value ? 'src' : '' }, value || missing()));
  const yesNo = (v) => (v === true ? 'Yes' : v === false ? 'No' : null);
  const undecided = () => el('span', { class: 'chip warn' }, 'to be decided');
  const choice = (label, value) => el('tr', {},
    el('td', { style: 'width:320px;color:var(--muted)' }, label), el('td', {}, value || undecided()));
  const accounts = data.bank_accounts || [];

  return [
    card('The person the return is for', table(null, [
      row('Name', a.name),
      row('PAN', a.pan, true),
      row('Date of birth', a.date_of_birth),
      row('Aadhaar, last four digits', a.aadhaar_last_four, true),
      row('Address', a.address),
      row('E-mail', a.email),
      row('Mobile', a.mobile, true),
    ]), '', el('span', { class: 'src', title: a.found_in || '' }, a.found_in ? `from ${clip(a.found_in, 70)}` : '')),
    card(`Bank accounts held in India (${accounts.length})`,
      accounts.length
        ? table(['Bank', 'IFSC', 'Account number', 'Type', 'For any refund', 'Seen in'],
            accounts.map((b) => el('tr', {},
              el('td', {}, b.bank_name),
              el('td', { class: 'src' }, b.ifsc),
              el('td', { class: 'src' }, b.account_number),
              el('td', {}, b.account_type || ''),
              el('td', {}, yesNo(b.for_refund) || undecided()),
              el('td', { class: 'src', title: b.found_in || '' }, clip(baseName(b.found_in || ''), 44)))))
        : el('div', { class: 'card-body empty' }, 'No bank account could be listed from the documents.'),
      '', el('span', { class: 'src' }, 'every account held must be listed; one is nominated for a refund')),
    card('Filing choices', table(null, [
      choice('Filed under section', filing.return_section),
      choice('Acknowledgement of the original return, if this revises one', filing.original_ack_number),
      choice('Opting out of the new regime, section 115BAC', yesNo(filing.opting_out_of_115BAC)),
      choice('Form 10-IEA acknowledgement', filing.form_10IEA_ack),
      choice('Governed by the Portuguese Civil Code, section 5A', yesNo(filing.portuguese_civil_code_5A)),
    ]), '', el('span', { class: 'src' }, 'decided by you, not stated by any document')),
  ];
}

const RENDERERS = {
  general: renderGeneral,
  scrip_112a: renderSchedule112A,
  depreciation: renderDepreciation,
  setoff_cfl: renderSetoff,
  foreign_special: renderForeign,
  salary: renderSalary,
  other_sources: renderOtherSources,
  deductions: renderDeductions,
  taxes_paid: renderTaxesPaid,
  capital_gains: renderCapitalGains,
  summary: renderSummary,
  business_computation: renderBusiness,
};

/* ---------------------------------------------------------- profiles tab */

async function profileAction(payload) {
  try {
    await api('/api/profiles', { method: 'POST', body: JSON.stringify(payload) });
  } catch (err) {
    toast(err.message, 'err');
    return false;
  }
  await refresh();
  return true;
}

/** A return's name as a folder name, the way the server makes it
 *  (paths.folder_name): less what a file system refuses. */
function folderName(name) {
  return String(name || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, ' ')
    .replace(/^[ .]+|[ .]+$/g, '').replace(/\s+/g, ' ') || 'profile';
}

/** The folder a return called `name` keeps in the Flow home, on this machine. */
function returnFolderPath(name, ...inside) {
  const home = String(state.home?.path || '').replace(/[\\/]+$/, '');
  const sep = home.includes('\\') ? '\\' : '/';
  return [home, folderName(name), ...inside].filter(Boolean).join(sep);
}

/** A folder as it is thought of: relative to the Flow home when inside it. */
function shortPath(path) {
  const home = String(state.home?.path || '').replace(/[\\/]+$/, '');
  const text = String(path || '');
  return home && text.toLowerCase().startsWith(home.toLowerCase()) && /[\\/]/.test(text[home.length] || '')
    ? text.slice(home.length + 1) : text;
}

/** The warning before a return's folder moves. Resolves true only when
 *  the move is confirmed. */
function confirmFolderMove(title, paragraphs, label) {
  const dialog = $('#move-dialog');
  $('#move-title').textContent = title;
  $('#move-message').replaceChildren(...paragraphs.filter(Boolean)
    .map((t) => (typeof t === 'string' ? el('p', {}, t) : t)));
  $('#move-confirm').textContent = label;
  dialog.returnValue = '';
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'move'), { once: true });
    dialog.showModal();
  });
}

const CLOSE_OPEN_FILES = 'Close any file from it that is open, such as results.xlsx in Excel, first.';

/** Financial years to choose from: the current one and the six before it,
 *  newest first. A year already chosen stays in the list even if older. */
function fyOptions(keep) {
  const now = new Date();
  const start = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  const years = [];
  for (let y = start; y > start - 7; y -= 1) years.push(`${y}-${String(y + 1).slice(-2)}`);
  if (keep && !years.includes(keep)) years.push(keep);
  return years.map((fy) => el('option', { value: fy },
    `FY ${fy} (AY ${+fy.slice(0, 4) + 1}-${String(+fy.slice(0, 4) + 2).slice(-2)})`));
}

function fySelect(value, attrs = {}) {
  const box = el('select', attrs, fyOptions(value));
  box.value = value || box.options[1]?.value || box.options[0]?.value || '';
  return box;
}

function profileInitials(name) {
  const words = String(name || '?').replace(/[^A-Za-z0-9 ]+/g, ' ').trim().split(/\s+/);
  return ((words[0] || '?')[0] + (words[1] ? words[1][0] : (words[0] || '').slice(1, 2))).toUpperCase();
}

/** Opens one of a return's folders in the file manager. */
async function openReturnFolder(id, which) {
  try {
    await api('/api/open-folder', { method: 'POST', body: JSON.stringify({ id, which }) });
  } catch (err) {
    toast(`Could not open the folder: ${err.message}`, 'err');
  }
}

/** Where the list of returns, the rates and every return's folders are kept. */
function homeCard() {
  const home = state.home || {};
  const cloud = home.cloud || [];
  return el('details', { class: 'card ret-home' },
    el('summary', {}, el('b', {}, 'Where your files are kept'),
      el('span', { class: 'where-v', title: home.path || '' }, home.path || '')),
    el('div', { class: 'card-body' },
      el('p', {}, `This folder (chosen by ${home.source || 'the default'}) holds everything personal: the `
        + 'list of returns, looked-up exchange rates and each return’s documents and results. By '
        + `convention a return called X has a folder X, with its documents in X/${home.input_folder || 'documents'} `
        + 'and everything Flow ITR produces from them beside it. The documents can be kept elsewhere.'),
      el('p', {}, 'To keep it somewhere else, set the FLOW_HOME environment variable, or put a file '
        + 'called flow.local.json beside the program containing {"home": "D:/somewhere"}, and restart.'),
      el('p', {}, cloud.length
        ? `${cloud.map((c) => `${c.kind} is at ${c.path}`).join('; ')}. “Put on ${cloud[0].kind}” moves a `
          + 'return’s documents there; the return’s own folder stays in the Flow home.'
        : 'Google Drive: with Google Drive for desktop installed, a Drive is an ordinary folder (for example '
          + 'G:/My Drive), and a return is put on it by giving that path as its folders.')));
}

/** A return's documents into a synced Drive folder, contents and all. */
async function putOnDrive(p, drive) {
  // Each Flow app keeps to its own folder under Flow/ on the Drive.
  const base = `${drive.path}/Flow/ITR/${p.name}`;
  if (!confirm(`Move the documents of "${p.name}" to ${drive.kind}?

${base}/${state.home.input_folder}

${drive.kind} will upload them to your Google account and keep them in step. `
    + `Flow ITR itself sends nothing anywhere. Wait for Drive to finish syncing before `
    + `working on another machine. The return’s own folder stays in the Flow home.`)) return;
  await profileAction({ action: 'move', id: p.id, field: 'source_dir',
                      target: `${base}/${state.home.input_folder}` });
}

// Which settings sit in which section of a return. Anything added to
// profiles.FIELDS later and not named here lands under the tax settings.
const RETURN_SECTIONS = {
  person: ['dob', 'age_band', 'sex'],
  tax: ['regime', 'audit_44ab'],
  reading: ['engine', 'excel_export'],
};

/** One setting of a return as a form control, reporting changes to `onChange`. */
function settingControl(key, field, value, onChange) {
  const id = `ret-${key}`;
  let box;
  if (field.options && field.options.length) {
    // Options that name a group (an engine's models) sit under that group.
    const option = (o) => el('option', { value: o.value, title: o.note || '' }, o.label);
    const kids = [];
    let group = null;
    for (const o of field.options) {
      if (!o.group) { kids.push(option(o)); group = null; continue; }
      if (!group || group.label !== o.group) { group = el('optgroup', { label: o.group }); kids.push(group); }
      group.append(option(o));
    }
    box = el('select', { id, onchange: (e) => onChange(key, e.target.value, true) }, kids);
    box.value = value ?? field.default ?? '';
  } else {
    box = el('input', { id, type: field.kind === 'date' ? 'date' : 'text', value: value || '',
                        oninput: (e) => onChange(key, e.target.value, true) });
  }
  const chosen = (field.options || []).find((o) => o.value === box.value);
  return el('div', { class: 'ret-field' },
    el('label', { for: id }, field.label), box,
    chosen?.note || field.note ? el('small', {}, chosen?.note || field.note) : null);
}

/** One titled part of a return's card. */
const retSection = (title, hint, ...body) => el('section', { class: 'ret-section' },
  el('div', { class: 'ret-section-h' }, el('h3', {}, title), hint ? el('p', {}, hint) : null), ...body);
const retGrid = (...kids) => el('div', { class: 'ret-grid' }, kids);

const RETURN_HINT = 'What it is called and which year it is for. The name identifies the return, '
  + 'and its folder is named after it.';

/** A return's folder, read-only under its name: it follows the name, so there
 *  is nothing to choose. The path can still be selected and copied. */
const folderBox = (id, path) => el('input', { id, class: 'ret-readonly', readonly: '', spellcheck: 'false',
                                              value: path || '', title: path || '',
                                              placeholder: 'Follows the return name' });
const returnFolderField = (box, note, after = null) => el('div', { class: 'ret-field ret-span' },
  el('label', { for: box.id }, 'Folder'), box, note, after);

/** The selected return: everything about it, changed with one Save. */
function returnDetail(p, isActive, store) {
  const ui = state.ui.returns;
  const draft = ui.draft;
  const fields = state.profileFields || {};
  const settings = { ...(p.settings || {}), ...(draft.settings || {}) };
  const dirty = () => Object.keys(draft).length > 0;

  const mark = () => {
    const bar = $('#ret-save');
    if (!bar) return;
    bar.hidden = !dirty();
  };
  const change = (key, value) => {
    if (['name', 'fy', 'pan'].includes(key)) {
      if (String(value) === String(p[key] ?? '')) delete draft[key]; else draft[key] = value;
    } else {
      draft.settings = draft.settings || {};
      if (String(value) === String((p.settings || {})[key] ?? fields[key]?.default ?? '')) delete draft.settings[key];
      else draft.settings[key] = value;
      if (!Object.keys(draft.settings).length) delete draft.settings;
    }
    mark();
  };
  const input = (key, label, value, attrs = {}) => el('div', { class: 'ret-field' },
    el('label', { for: `ret-${key}` }, label),
    el('input', { id: `ret-${key}`, value: value || '', ...attrs, oninput: (e) => change(key, e.target.value) }),
    attrs.note ? el('small', {}, attrs.note) : null);
  const settingsOf = (group) => (group === 'tax'
    ? [...RETURN_SECTIONS.tax, ...Object.keys(fields).filter((k) => !Object.values(RETURN_SECTIONS).flat().includes(k))]
    : RETURN_SECTIONS[group]).filter((k) => fields[k]).map((k) => settingControl(k, fields[k], settings[k], change));

  const fy = fySelect(draft.fy ?? p.fy, { id: 'ret-fy', onchange: (e) => change('fy', e.target.value) });
  const sharedWith = (store.profiles || []).filter((o) => o.id !== p.id && o.source_path === p.source_path).map((o) => o.name);

  // The name identifies the return and its folder is named after it, so the
  // folder sits under the name, read-only, saying where a new name moves it.
  // Its results inside are Flow ITR's business, unless an earlier version left
  // them elsewhere and they need moving in.
  const folderNote = el('small', {});
  const showFolder = (name) => {
    const moving = !!name.trim() && folderName(name).toLowerCase() !== folderName(p.name).toLowerCase();
    folderNote.textContent = moving
      ? `Moves to ${returnFolderPath(name)} when you save.`
      : 'Named after the return. Renaming the return moves it, with everything in it.';
    folderNote.classList.toggle('ret-pending', moving);
  };
  showFolder(draft.name ?? p.name);
  const moveResultsIn = async () => {
    const ok = await confirmFolderMove('Move the results into the return’s folder?', [
      `This return’s results are in ${shortPath(p.data_path)}, outside its own folder. They move to:`,
      el('p', { class: 'ret-path' }, p.conventional_data_path),
      `Nothing needs to be redone. ${CLOSE_OPEN_FILES}`,
    ], 'Move them');
    if (ok && await profileAction({ action: 'convention', id: p.id })) {
      toast(`Moved the results to ${p.conventional_data_path}.`);
    }
  };
  const nameField = el('div', { class: 'ret-field' },
    el('label', { for: 'ret-name' }, 'Return name'),
    el('input', { id: 'ret-name', value: draft.name ?? p.name, spellcheck: 'false',
                  oninput: (e) => { change('name', e.target.value); showFolder(e.target.value); } }));
  const folderField = returnFolderField(folderBox('ret-folder', p.folder_path || returnFolderPath(p.name)),
    folderNote,
    p.data_conventional === false ? el('div', { class: 'ret-legacy' },
      chip('its results are kept elsewhere', 'warn'),
      el('button', { class: 'ghost small', type: 'button', onclick: moveResultsIn,
                     title: 'Keep this return’s results in its own folder.' }, 'Move them here…')) : null);

  // The documents are the one folder a return chooses: by default in its own
  // folder, or wherever the papers already are. "Change location" points the
  // return elsewhere and moves nothing; "Move…" carries the files along.
  const documents = el('div', { class: 'ret-folder' });
  const viewDocuments = () => documents.replaceChildren(...[
    el('div', { class: 'ret-path', title: p.source_path }, p.source_path || '—'),
    p.source_path_exists ? null : el('div', {}, chip('not found on this machine', 'warn')),
    el('div', { class: 'ret-folder-acts' },
      el('button', { class: 'ghost small', type: 'button', onclick: () => openReturnFolder(p.id, 'source') },
         icon('documents'), 'Open'),
      el('button', { class: 'ghost small', type: 'button', onclick: (e) => copyText(p.source_path || '', e.currentTarget) },
         icon('copy'), 'Copy path'),
      el('button', { class: 'ghost small', type: 'button', onclick: editDocuments,
                     title: 'Use another folder. Nothing is moved or copied.' }, icon('pencil'), 'Change location'),
      el('button', { class: 'ghost small', type: 'button',
                     title: 'Carry this folder’s contents to a new place, and use that.',
                     onclick: () => {
        // Offered the return's own folder first: that is where documents belong
        // unless they are deliberately kept somewhere else.
        const target = prompt('Move the documents to which folder? Everything in it moves too.',
                              p.source_conventional === false ? p.conventional_source_path : p.source_path);
        if (target && target !== p.source_path) {
          profileAction({ action: 'move', id: p.id, field: 'source_dir', target });
        }
      } }, 'Move…')),
  ].filter(Boolean));
  const editDocuments = () => {
    const box = el('input', { value: p.source_path || '', spellcheck: 'false', class: 'ret-path-input',
      onkeydown: (e) => { if (e.key === 'Enter') use(); if (e.key === 'Escape') viewDocuments(); } });
    const use = async () => {
      const target = box.value.trim();
      if (!target || target === p.source_path) { viewDocuments(); return; }
      if (await profileAction({ action: 'update', id: p.id, patch: { source_dir: target } })) {
        toast('Documents are now read from the new folder. Sort the documents again so each schedule finds its papers.');
      }
    };
    documents.replaceChildren(
      box,
      el('small', { class: 'ret-hint' },
        'Paste the full path of the folder that holds the documents, for example D:\\Tax\\2025-26 or G:\\My Drive\\Tax. Nothing is moved or copied; the current folder is left as it is.'),
      el('div', { class: 'ret-folder-acts' },
        el('button', { class: 'primary small', type: 'button', onclick: use }, 'Use this folder'),
        el('button', { class: 'ghost small', type: 'button', onclick: viewDocuments }, 'Cancel')));
    box.focus();
    box.select();
  };
  viewDocuments();
  const documentsHint = sharedWith.length
    ? `Shared with ${sharedWith.join(', ')}: the same papers, read into separate returns.`
    : p.source_conventional
      ? 'Kept in the return’s folder. Point the return at another folder only if your papers are already '
        + 'somewhere else, such as Google Drive.'
      : 'Read from a folder outside the return’s folder.';

  const save = async () => {
    const patch = { ...draft };
    if (!Object.keys(patch).length) return;
    // The return's folder is named after it, so a new name moves the folder:
    // the results always, the documents when they are in it. Never without
    // this warning; the server refuses a rename that was not confirmed.
    const newName = (patch.name ?? p.name).trim();
    const renamed = !!newName && folderName(newName).toLowerCase() !== folderName(p.name).toLowerCase();
    const newFolder = returnFolderPath(newName);
    if (renamed) {
      const docsMove = p.source_conventional;
      const ok = await confirmFolderMove(`Rename to “${newName}”?`, [
        'A return’s folder is named after it, so renaming it moves the folder to:',
        el('p', { class: 'ret-path' }, newFolder),
        (docsMove && p.data_conventional
          ? `Its documents and results move from ${shortPath(returnFolderPath(p.name))}.`
          : `Its results move from ${shortPath(p.data_path)}`
            + (docsMove ? ` and its documents from ${shortPath(p.source_path)}.` : '.'))
          + ' Nothing needs to be redone.',
        docsMove && sharedWith.length
          ? `${sharedWith.join(', ')} also ${sharedWith.length > 1 ? 'read' : 'reads'} these documents, `
            + 'and will read them from the new folder.' : '',
        docsMove ? '' : `The documents stay in ${shortPath(p.source_path)}, outside the return’s folder.`,
        CLOSE_OPEN_FILES,
      ], 'Rename and move');
      if (!ok) return;
      patch.move_folder = true;
    }
    ui.draft = {};
    if (await profileAction({ action: 'update', id: p.id, patch })) {
      toast(renamed ? `Renamed. Its folder is now ${newFolder}.` : `Saved the changes to ${newName}.`);
    } else {
      ui.draft = patch;               // refused: keep what was typed
    }
    renderProfiles();
  };

  return el('div', { class: 'ret-detail' },
    el('div', { class: 'ret-head' },
      el('span', { class: 'ret-avatar big' }, profileInitials(p.name)),
      el('div', { class: 'ret-head-t' },
        el('h2', {}, p.name),
        el('div', { class: 'ret-meta' }, `FY ${p.fy} · AY ${p.ay} · ITR-3 · resident and ordinarily resident`)),
      isActive
        ? el('span', { class: 'chip ok ret-inuse' }, icon('check'), 'In use')
        : el('button', { class: 'primary', type: 'button',
                         onclick: async () => {
                           // Another return may be another year: start its state afresh.
                           state.ay = null; state.runs = {};
                           if (await profileAction({ action: 'activate', id: p.id })) toast(`Now working on ${p.name}.`);
                         } },
             'Use this return')),
    el('div', { class: 'card ret-card' },
      retSection('Return', RETURN_HINT,
        retGrid(nameField,
          el('div', { class: 'ret-field' }, el('label', { for: 'ret-fy' }, 'Financial year'), fy,
             el('small', {}, 'Tax rates are built in for FY 2025-26.')),
          folderField)),
      retSection('The person', 'The PAN and date of birth also open the password-protected AIS, TIS and Form 26AS.',
        retGrid(
          input('pan', 'PAN', draft.pan ?? p.pan, { placeholder: 'AAAAA9999A', maxlength: '10',
                style: 'text-transform:uppercase' }),
          ...settingsOf('person'))),
      retSection('How the tax is worked out', null, retGrid(...settingsOf('tax'))),
      retSection('Reading and export', null,
        retGrid(...settingsOf('reading'),
          el('div', { class: 'ret-field ret-note' },
            el('a', { class: 'linkish', href: '#engines' }, 'Reading engine settings and local models'),
            el('small', {}, 'Models, time limits, and open models that run on this computer.')))),
      retSection('Documents', documentsHint,
        documents,
        (state.home?.cloud || []).length ? el('div', { class: 'ret-drive' },
          (state.home.cloud || []).map((drive) => el('button', { class: 'ghost small', type: 'button',
            onclick: () => putOnDrive(p, drive) }, `Put on ${drive.kind}`))) : null),
      el('div', { class: 'ret-save', id: 'ret-save', hidden: !dirty() },
        el('span', {}, 'You have unsaved changes.'),
        el('button', { class: 'ghost', type: 'button', onclick: () => { ui.draft = {}; renderProfiles(); } }, 'Discard'),
        el('button', { class: 'primary', type: 'button', onclick: save }, 'Save changes'))),
    el('details', { class: 'ret-danger' },
      el('summary', {}, 'Remove this return'),
      el('p', {}, 'Removes it from the list only. Its folder and documents stay on disk, and a new '
                  + 'return with the same name uses that folder again.'),
      el('button', { class: 'ghost danger', type: 'button', disabled: store.profiles.length < 2,
        title: store.profiles.length < 2 ? 'This is the only return; add another before removing it.' : '',
        onclick: async () => {
          if (!confirm(`Remove the return "${p.name}" from the list? Its files stay on disk.`)) return;
          if (await profileAction({ action: 'delete', id: p.id })) { ui.draft = {}; select('_profiles'); }
        } }, 'Remove from the list')));
}

/** A new return: a name and a year; its folder follows the name. */
function newReturnForm() {
  let typedSource = false;
  const docsDefault = (n) => (n.trim() ? `${folderName(n)}/${state.home?.input_folder || 'documents'}` : '');
  const src = el('input', { id: 'np-src', spellcheck: 'false', oninput: () => { typedSource = true; } });
  const folderPath = folderBox('np-folder', '');
  const name = el('input', { id: 'np-name', placeholder: 'for example Asha 2025-26', autofocus: '', spellcheck: 'false',
    oninput: (e) => {
      folderPath.value = folderPath.title = e.target.value.trim() ? returnFolderPath(e.target.value) : '';
      if (!typedSource) src.value = docsDefault(e.target.value);
    } });
  const create = async () => {
    const wanted = name.value.trim();
    if (!wanted) { name.focus(); return; }
    state.ay = null; state.runs = {};
    if (await profileAction({ action: 'create', name: wanted, fy: $('#np-fy').value, pan: $('#np-pan').value,
                              source_dir: src.value })) {
      const made = (state.profiles?.profiles || []).find((x) => x.name === wanted);
      toast(`Added ${wanted}. It is now the return in use.`);
      select('_profiles', made?.id || null);
    }
  };
  return el('div', { class: 'ret-detail' },
    el('div', { class: 'ret-head' },
      el('span', { class: 'ret-avatar big new' }, '+'),
      el('div', { class: 'ret-head-t' }, el('h2', {}, 'New return'),
        el('div', { class: 'ret-meta' }, 'One person and one financial year. Everything else can be set afterwards.'))),
    el('div', { class: 'card ret-card' },
      retSection('Return', RETURN_HINT,
        retGrid(
          el('div', { class: 'ret-field' }, el('label', { for: 'np-name' }, 'Return name'), name),
          el('div', { class: 'ret-field' }, el('label', { for: 'np-fy' }, 'Financial year'), fySelect(state.fy, { id: 'np-fy' })),
          returnFolderField(folderPath, el('small', {}, 'Made when the return is created.')))),
      retSection('The person', 'The PAN and date of birth open the password-protected AIS, TIS and Form 26AS. '
                 + 'Both can be added later.',
        retGrid(el('div', { class: 'ret-field' }, el('label', { for: 'np-pan' }, 'PAN (optional)'),
          el('input', { id: 'np-pan', placeholder: 'AAAAA9999A', maxlength: '10', style: 'text-transform:uppercase' })))),
      retSection('Documents', 'Kept in the return’s folder. Choose another folder only if your papers are '
                 + 'already somewhere else, such as Google Drive.',
        el('details', { class: 'ret-advanced' },
          el('summary', {}, 'Use a different documents folder'),
          retGrid(el('div', { class: 'ret-field ret-span' }, el('label', { for: 'np-src' }, 'Documents folder'), src)))),
      el('div', { class: 'ret-save' },
        el('span', {}, 'The new return becomes the one in use.'),
        el('button', { class: 'ghost', type: 'button', onclick: () => select('_profiles') }, 'Cancel'),
        el('button', { class: 'primary', type: 'button', onclick: create }, 'Create return'))));
}

function renderProfiles() {
  const store = state.profiles || { profiles: [], active: null };
  const ui = (state.ui.returns ||= { draft: {}, shown: null });
  const panel = $('#panel');
  const wanted = state.sub;
  const isNew = wanted === 'new';
  const current = isNew ? null
    : store.profiles.find((p) => p.id === wanted) || store.profiles.find((p) => p.id === store.active) || store.profiles[0];
  // A draft belongs to the return it was typed for.
  const shownKey = isNew ? 'new' : current?.id;
  if (ui.shown !== shownKey) { ui.draft = {}; ui.shown = shownKey; }

  const go = (id) => (e) => {
    if (Object.keys(ui.draft).length && !confirm('Discard the unsaved changes?')) { e.preventDefault(); return; }
    ui.draft = {};
  };
  const regimeName = (p) => ({ new: 'New regime', old: 'Old regime', compare: 'Both regimes' }[p.settings?.regime] || '');

  const list = el('nav', { class: 'ret-list', 'aria-label': 'Returns' },
    store.profiles.map((p) => el('a', {
      class: 'ret-item' + (current && p.id === current.id ? ' selected' : ''),
      href: `#_profiles/${p.id}`, onclick: go(p.id),
      'aria-current': current && p.id === current.id ? 'true' : null,
    },
      el('span', { class: 'ret-avatar' }, profileInitials(p.name)),
      el('span', { class: 'ret-item-t' },
        el('b', {}, p.name),
        el('small', {}, [`FY ${p.fy}`, regimeName(p)].filter(Boolean).join(' · '))),
      p.id === store.active ? el('span', { class: 'chip ok' }, 'In use') : null)),
    el('a', { class: 'ret-item add' + (isNew ? ' selected' : ''), href: '#_profiles/new', onclick: go('new') },
      el('span', { class: 'ret-avatar new' }, '+'), el('span', { class: 'ret-item-t' }, el('b', {}, 'New return'))));

  panel.replaceChildren(
    el('div', { class: 'page-head' },
      el('div', {},
        el('div', { class: 'page-title' }, el('h1', {}, 'Returns')),
        el('p', { class: 'page-sub' },
          'A return holds everything for one income-tax return: whose it is and for which year, how the tax '
          + 'is to be worked out, the documents it reads, and all that comes from them: the figures read, your '
          + 'corrections and decisions, the computation, the reconciliation and the Excel workbook.'),
        el('p', { class: 'page-sub' },
          'Each return keeps its own, so two can sit side by side, even for the same person and year, to compare '
          + 'regimes or reading engines. The one marked In use is what every other page shows.'))),
    el('div', { class: 'ret-layout' },
      list,
      isNew ? newReturnForm() : current ? returnDetail(current, current.id === store.active, store)
            : el('div', { class: 'empty-state' }, el('h3', {}, 'No returns yet'))),
    homeCard());
}

/* ------------------------------------------------------------- settings */

/** Light, dark, or whatever the machine is set to.
 *
 * The choice is stored per browser, not in the profile: it is about the person
 * looking at the screen, not about the return. "Match the system" is the
 * default and means exactly that -- it keeps following the setting as it
 * changes through the day.
 */
function applyTheme(choice) {
  const root = document.documentElement;
  if (choice === 'light' || choice === 'dark') root.dataset.theme = choice;
  else delete root.dataset.theme;
  try { localStorage.setItem('flow-theme', choice); } catch { /* private window */ }
  document.querySelectorAll('[data-theme-choice]').forEach((b) =>
    b.setAttribute('aria-checked', String(b.dataset.themeChoice === choice)));
}

function currentTheme() {
  try { return localStorage.getItem('flow-theme') || 'system'; } catch { return 'system'; }
}

/* -------------------------------------------------------------- actions */

async function runTab(tab) {
  const run = runOf(tab.id);
  const before = balance();
  run.running = true;
  run.log = [];
  run.lastRun = null;
  renderPanel();
  renderRail();
  renderHeader();

  const engine = engineId();
  const body = JSON.stringify({
    ay: state.ay,
    tab: tab.id,
    engine,
    // "Read again" means read again: a schedule that already has a reading
    // is re-read even when its documents have not changed. A first reading
    // has nothing to reuse either way.
    force: Boolean(tab.document),
  });

  const endpoint = tab.kind === 'derive' ? '/api/compute' : '/api/run';
  try {
    const res = await api(endpoint, { method: 'POST', body });
    if (endpoint === '/api/compute') {
      run.log.push({ phase: 'done', detail: 'recomputed' });
      run.lastRun = { tab: tab.id, status: 'ok', engine };
    } else {
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
          if (evt.phase === 'done') {
            run.log.push({ phase: 'done', detail: `${evt.result.status} · ${evt.result.run_id || ''}` });
            run.lastRun = { tab: tab.id, engine, ...evt.result };
            if (evt.result.status === 'stopped') {
              run.lastRun.errors = (run.log.find((x) => x.phase === 'stopped') || {}).detail || evt.result.errors;
            }
          } else {
            if (evt.phase === 'error') run.lastRun = { tab: tab.id, engine, status: 'failed', errors: evt.detail };
            run.log.push(evt);
          }
          // Only the progress strip is repainted while a run streams: redrawing
          // the schedule on every line would fold away whatever was open.
          runProgress(tab.id);
        }
      }
    }
  } catch (err) {
    run.log.push({ phase: 'error', detail: err.message });
    run.lastRun = { tab: tab.id, engine, status: 'failed', errors: err.message };
  } finally {
    // Whatever happened, the button must come back. A run that dies leaving
    // "Running…" on screen is indistinguishable from one that did nothing.
    run.running = false;
  }
  await refresh().catch(() => renderPanel());
  // What the run did to the one figure everything leads to.
  if (run.lastRun?.status === 'stopped') {
    toast(`${tabName(tab.id)}: stopped. Nothing from that reading was saved.`);
  } else if (run.lastRun && run.lastRun.status !== 'failed') {
    toast(balanceChange(before, balance(),
      `${tabName(tab.id)} ${tab.kind === 'derive' ? 'recomputed' : 'read'}.`));
  }
}

let pendingPointer = null;
let pendingTab = null;

/** The correction dialog. `tab` is the schedule the figure belongs to, which
 *  is not always the page on screen: a figure can be opened from Search. */
function openOverride(pointer, current, tab) {
  pendingPointer = pointer;
  pendingTab = tab || state.current;
  $('#ov-pointer').textContent = pointer;
  $('#ov-was').value = rupees(current);
  $('#ov-value').value = current ?? '';
  $('#ov-reason').value = '';
  $('#override-dialog').showModal();
}

async function ensureSchema(id) {
  if (!state.tabs.some((t) => t.id === id) || state.schemas[id] !== undefined) return;
  try {
    state.schemas[id] = await getJSON(`/api/schema?tab=${id}`);
  } catch {
    state.schemas[id] = null;   // derive tabs have no schedule schema
  }
}

/** The server's own code changed after it started. Reloading the page cannot
 *  help: until Flow ITR is restarted, anything new answers "not found". */
function showRestartBanner() {
  if ($('#restart-banner')) return;
  $('#stale-banner')?.remove();
  document.body.prepend(el('div', { id: 'restart-banner', class: 'stale-banner', role: 'status' },
    'Flow ITR has been updated since it was started, so parts of this page may not work. Restart it to use the '
    + 'changes: close its window (or press Ctrl+C in it), run flow.cmd again, then reload this page.'));
}

function showStaleBanner() {
  if ($('#stale-banner') || $('#restart-banner')) return;
  const bar = el('div', { id: 'stale-banner', class: 'stale-banner', role: 'status' },
    'This page has been updated since you opened it; what you see may be the old version. ',
    el('button', { class: 'primary small', onclick: () => location.reload() }, 'Reload'));
  document.body.prepend(bar);
}
