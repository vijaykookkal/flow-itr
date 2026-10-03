/* Help and about, and local models.
 *
 * The user guide is the README itself, rendered here, so there is one text to
 * keep right rather than two. The renderer covers what that file uses --
 * headings, paragraphs, lists, tables, code, links, bold -- and builds DOM
 * nodes, never HTML strings. Pictures from other sites (the README's badges)
 * are left out: the page loads nothing from the network.
 */

const REPO_URL = 'https://github.com/vijaykookkal/flow-itr';
const HELP_DOCS = {};

/** GitHub's heading anchors, so the README's own links between sections work. */
const mdSlug = (text) => String(text).toLowerCase().trim().replace(/[^\w\s-]/g, '').replace(/\s/g, '-');

function mdLink(text, href) {
  if (href.startsWith('#')) {
    return el('a', { href: '#about', onclick: (e) => {
      e.preventDefault();
      $(`#md-${href.slice(1)}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    } }, ...mdInline(text));
  }
  const url = /^[a-z]+:/i.test(href) ? href : `${REPO_URL}/blob/main/${href}`;
  return el('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, ...mdInline(text));
}

function mdInline(text) {
  const out = [];
  const re = /(`[^`]+`)|(!\[[^\]]*\]\([^)]*\))|(\[[^\]]+\]\([^)\s]+\))|(\*\*[^*]+\*\*)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (m[1]) out.push(el('code', {}, t.slice(1, -1)));
    else if (m[3]) {
      const parts = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(t);
      out.push(mdLink(parts[1], parts[2]));
    } else if (m[4]) out.push(el('b', {}, ...mdInline(t.slice(2, -2))));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Markdown to nodes, with the second-level headings for a contents list. */
function mdRender(text) {
  const lines = String(text || '').replace(/\r/g, '').split('\n');
  const blocks = [];
  const toc = [];
  const isBullet = (t) => /^([-*]|\d+\.)\s+/.test(t);
  const startsBlock = (t) => /^(#{1,6}\s|```|\||---+$)/.test(t) || isBullet(t);
  let i = 0;
  while (i < lines.length) {
    const t = lines[i].trim();
    if (!t) { i += 1; continue; }
    if (/^(!\[|\[!\[)/.test(t)) { i += 1; continue; }               // badges
    if (t.startsWith('```')) {
      const buf = [];
      const indent = lines[i].match(/^\s*/)[0].length;
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        buf.push(lines[i].slice(Math.min(indent, lines[i].match(/^\s*/)[0].length)));
        i += 1;
      }
      i += 1;
      blocks.push(el('pre', { class: 'md-code' }, el('code', {}, buf.join('\n'))));
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(t);
    if (h) {
      const level = h[1].length;
      const id = `md-${mdSlug(h[2])}`;
      blocks.push(el(`h${Math.min(level + 1, 5)}`, { id, class: 'md-h' }, ...mdInline(h[2])));
      if (level === 2) toc.push({ id, text: h[2] });
      i += 1;
      continue;
    }
    if (/^---+$/.test(t)) { blocks.push(el('hr', {})); i += 1; continue; }
    if (t.startsWith('|')) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i += 1;
      }
      const [head, ...body] = rows;
      blocks.push(el('div', { class: 'md-table' }, el('table', {},
        el('thead', {}, el('tr', {}, head.map((c) => el('th', {}, ...mdInline(c))))),
        el('tbody', {}, body.map((r) => el('tr', {}, r.map((c) => el('td', {}, ...mdInline(c)))))))));
      continue;
    }
    if (isBullet(t)) {
      const ordered = /^\d+\./.test(t);
      const items = [];
      const start = ordered ? Number(t.match(/^\d+/)[0]) : null;
      while (i < lines.length) {
        const cur = lines[i].trim();
        if (cur && isBullet(cur) && (/^\d+\./.test(cur) === ordered)) {
          items.push(cur.replace(/^([-*]|\d+\.)\s+/, ''));
          i += 1;
          // Continuation lines belong to the item; a code block or table
          // inside it ends the list and is drawn on its own.
          while (i < lines.length && lines[i].trim() && /^\s{2,}/.test(lines[i])
                 && !startsBlock(lines[i].trim())) {
            items[items.length - 1] += ` ${lines[i].trim()}`;
            i += 1;
          }
          if (i < lines.length && !lines[i].trim() && i + 1 < lines.length && isBullet(lines[i + 1].trim())
              && (/^\d+\./.test(lines[i + 1].trim()) === ordered)) i += 1;
          continue;
        }
        break;
      }
      blocks.push(el(ordered ? 'ol' : 'ul', { class: 'md-list', start: ordered && start !== 1 ? String(start) : null },
        items.map((it) => el('li', {}, ...mdInline(it)))));
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i].trim())) {
      para.push(lines[i].trim());
      i += 1;
    }
    blocks.push(el('p', {}, ...mdInline(para.join(' '))));
  }
  return { blocks, toc };
}

async function loadHelpDoc(name) {
  if (HELP_DOCS[name] !== undefined) return;
  HELP_DOCS[name] = null;
  try {
    HELP_DOCS[name] = (await getJSON(`/api/doc?name=${name}`)).text || '';
  } catch (err) {
    HELP_DOCS[name] = `Could not load this page: ${err.message}`;
  }
  if (state.current === 'about') renderPanel();
}

/** Help and about: the user guide, what's new, and about Flow. */
function pageAbout() {
  const tab = ['guide', 'changes', 'about'].includes(state.sub) ? state.sub : 'guide';
  const tabs = el('div', { class: 'tabs', role: 'tablist' },
    [['guide', 'User guide'], ['changes', 'What’s new'], ['about', 'About']].map(([id, label]) =>
      el('a', { class: 'tab', role: 'tab', href: `#about/${id}`, 'aria-selected': String(id === tab) }, label)));
  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('div', { class: 'page-title' }, el('h1', {}, 'Help and about')),
      el('p', { class: 'page-sub' }, `Flow ${state.version || ''} · the guide, what has changed, and who made it.`)));

  if (tab === 'about') return [head, tabs, aboutView()];
  const name = tab === 'guide' ? 'guide' : 'changes';
  if (HELP_DOCS[name] === undefined || HELP_DOCS[name] === null) {
    loadHelpDoc(name);
    return [head, tabs, el('div', { class: 'card md-wrap' }, el('div', { class: 'card-body muted' }, 'Loading…'))];
  }
  const { blocks, toc } = mdRender(HELP_DOCS[name]);
  // The first heading is the page's own title, already shown above.
  if (blocks[0]?.tagName === 'H2') blocks.shift();
  const contents = toc.length > 2 ? el('nav', { class: 'md-toc', 'aria-label': 'Contents' },
    el('b', {}, 'Contents'),
    toc.map((t) => el('a', { href: '#about', onclick: (e) => {
      e.preventDefault();
      $(`#${t.id}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    } }, t.text))) : null;
  return [head, tabs, el('div', { class: 'md-layout' + (contents ? '' : ' single') },
    contents, el('article', { class: 'card md' }, blocks))];
}

function aboutView() {
  const licence = HELP_DOCS.licence;
  if (licence === undefined) loadHelpDoc('licence');
  const holder = (/Copyright \(c\) (.+)/.exec(licence || '') || [])[1] || '';
  const engines = (state.engines || []).filter((e) => e.selectable && e.available).map((e) => e.label);
  const row = (k, v) => el('div', { class: 'about-row' }, el('span', {}, k), el('b', {}, v));
  return el('div', { class: 'about' },
    el('section', { class: 'card about-card' },
      el('div', { class: 'about-brand' },
        el('img', { src: 'logo.svg', alt: '', width: '48', height: '48' }),
        el('div', {}, el('h2', {}, 'Flow'), el('p', {}, 'An ITR-3 assistant for residents of India'))),
      el('div', { class: 'about-rows' },
        row('Version', state.version || '—'),
        row('Licence', 'MIT, free to use, change and share'),
        holder ? row('Copyright', holder) : null,
        row('Reading engines found', engines.length ? engines.join(', ') : 'none'),
        row('Your files', state.home?.path || '—')),
      el('div', { class: 'about-links' },
        el('a', { class: 'ghost', href: REPO_URL, target: '_blank', rel: 'noopener noreferrer' }, 'Source code on GitHub', icon('open')),
        el('a', { class: 'ghost', href: `${REPO_URL}/issues`, target: '_blank', rel: 'noopener noreferrer' }, 'Report a problem', icon('open')),
        el('a', { class: 'ghost', href: '#about/changes' }, 'What’s new'))),
    el('section', { class: 'card' },
      el('h2', {}, 'Privacy in one paragraph'),
      el('div', { class: 'card-body' },
        el('p', {}, 'Flow runs only on this computer and cannot be reached from another. It sends nothing over '
          + 'the internet itself. To read a document, Claude Code or Codex sends its contents to Anthropic or '
          + 'OpenAI under your own account; with a local model through Ollama, nothing leaves this computer at '
          + 'all. Your returns, documents and results stay in your Flow folder, never in the program.'))),
    el('section', { class: 'card' },
      el('h2', {}, 'Not tax advice'),
      el('div', { class: 'card-body' },
        el('p', {}, 'Flow prepares a draft for your review and files nothing. It is not affiliated with the '
          + 'Income Tax Department or any institution named in it. Check every figure against the e-filing '
          + 'utility, and ask a professional when the return is not simple.'),
        el('p', { class: 'muted' }, 'Typefaces: Figtree and IBM Plex Mono, under the SIL Open Font License.'))));
}

/* --------------------------------------------------------- reading engines */

let MODELS = null;
let ENGINE_SETTINGS = null;
let ENGINE_DRAFT = {};
let modelsTimer = null;
let modelsPulling = new Set();

async function loadModels() {
  modelsTimer = null;
  try {
    MODELS = await getJSON('/api/models');
  } catch (err) {
    MODELS = { running: false, error: err.message, installed: [], recommended: [], pulls: {} };
  }
  const active = new Set(Object.entries(MODELS.pulls || {}).filter(([, p]) => !p.done).map(([n]) => n));
  // A download that has just finished: the engine lists must hear of it.
  const finished = [...modelsPulling].filter((n) => !active.has(n));
  modelsPulling = active;
  if (finished.length) {
    await refresh();
    finished.forEach((n) => {
      const p = MODELS.pulls[n];
      toast(p?.error ? `${n} did not download: ${p.error}` : `${n} is ready. Choose it under Returns › Reading engine.`,
            p?.error ? 'err' : '');
    });
  }
  if (state.current === 'engines') renderPanel();
  clearTimeout(modelsTimer);
  if (active.size && state.current === 'engines') modelsTimer = setTimeout(loadModels, 2000);
}

async function loadEngineSettings() {
  try {
    ENGINE_SETTINGS = await getJSON('/api/settings');
  } catch (err) {
    toast(`Could not load the engine settings: ${err.message}`, 'err');
    ENGINE_SETTINGS = { current: {}, defaults: {}, choices: {} };
  }
  if (state.current === 'engines') renderPanel();
}

async function modelAction(action, name) {
  try {
    MODELS = await api('/api/models', { method: 'POST', body: JSON.stringify({ action, name }) }).then((r) => r.json());
  } catch (err) {
    toast(err.message, 'err');
    return;
  }
  if (action === 'remove') { toast(`${name} removed.`); await refresh(); }
  loadModels();
}

async function saveEngineSettings(patch) {
  try {
    ENGINE_SETTINGS = await api('/api/settings', { method: 'POST', body: JSON.stringify({ patch }) }).then((r) => r.json());
    ENGINE_DRAFT = {};
    toast('Saved. New readings use these settings.');
    await refresh();
  } catch (err) {
    toast(err.message, 'err');
  }
  renderPanel();
}

const gb = (bytes) => `${(bytes / 1e9).toFixed(1)} GB`;

/** The value in force for a setting, with what has been typed but not saved on top. */
function engineValue(path) {
  let draft = ENGINE_DRAFT;
  let cur = ENGINE_SETTINGS?.current || {};
  for (const key of path) {
    draft = draft && typeof draft === 'object' ? draft[key] : undefined;
    cur = cur && typeof cur === 'object' ? cur[key] : undefined;
  }
  return draft !== undefined ? draft : cur;
}

function setEngineDraft(path, value) {
  let node = ENGINE_DRAFT;
  path.slice(0, -1).forEach((key) => { node = (node[key] ||= {}); });
  node[path[path.length - 1]] = value;
  const bar = $('#eng-save');
  if (bar) bar.hidden = false;
}

/** Ollama: what is arriving, and models that can be added. */
function ollamaAdd(m) {
  const installed = (m.installed || []).filter((x) => !x.embedding);
  const pulls = Object.entries(m.pulls || {});
  const isInstalled = (name) => installed.some((x) => x.name === name || x.name === `${name}:latest`);
  const progress = (name, p) => {
    const share = p.total ? p.completed / p.total : 0;
    return el('div', { class: 'mdl-pull' + (p.error ? ' err' : '') },
      el('div', { class: 'mdl-pull-h' }, el('b', {}, name),
        el('span', {}, p.error ? `Stopped: ${p.error}`
          : p.done ? 'Ready'
          : p.total ? `${gb(p.completed)} of ${gb(p.total)} · ${Math.floor(share * 100)}%`
          : (p.status || 'Starting'))),
      p.error || p.done ? null : el('div', { class: 'mdl-bar' }, el('i', { style: `width:${(share * 100).toFixed(1)}%` })));
  };
  const custom = el('input', { placeholder: 'any model name from ollama.com/library, e.g. llama3.1:8b', spellcheck: 'false',
    onkeydown: (e) => { if (e.key === 'Enter' && custom.value.trim()) modelAction('pull', custom.value.trim()); } });

  return [
    pulls.some(([, p]) => !p.done || p.error) ? el('div', { class: 'eng-sub' },
      el('h4', {}, 'Downloading'),
      el('div', { class: 'mdl-pulls' }, pulls.filter(([, p]) => !p.done || p.error).map(([n, p]) => progress(n, p))),
      el('p', { class: 'muted' }, 'You can leave this page; the download carries on.')) : null,
    el('div', { class: 'eng-sub' },
      el('h4', {}, 'Add a model', el('small', {}, ' chosen for a laptop without a graphics card')),
      el('div', { class: 'mdl-grid' }, (m.recommended || []).map((r) => {
        const pulling = (m.pulls || {})[r.name];
        return el('div', { class: 'mdl-card' },
          el('div', { class: 'mdl-card-h' }, el('b', {}, r.name), el('span', { class: 'muted' }, r.size)),
          el('p', {}, r.note),
          isInstalled(r.name) ? chip('Installed', 'ok')
            : pulling && !pulling.done ? progress(r.name, pulling)
            : el('button', { class: 'ghost small', type: 'button', onclick: () => modelAction('pull', r.name) },
                icon('download'), 'Download'));
      })),
      el('div', { class: 'mdl-custom' },
        el('label', {}, 'Another model'), custom,
        el('button', { class: 'ghost', type: 'button', onclick: () => custom.value.trim() && modelAction('pull', custom.value.trim()) },
           icon('download'), 'Download')),
      el('p', { class: 'muted', style: 'margin-top:10px' },
        'Ollama keeps models in its own folder (usually .ollama in your user folder), not in your Flow folder.')),
  ];
}


/** What each engine costs and where documents go: the same facts for every
 *  engine, told in the same place. */
const ENGINE_FACTS = {
  claude: { costs: 'a Claude subscription', documents: 'sent to Anthropic to be read',
            install: 'Install the Claude Code command-line tool from claude.com/claude-code, run claude once to sign in, and restart Flow.' },
  codex: { costs: 'a ChatGPT subscription', documents: 'sent to OpenAI to be read',
           install: 'Install the Codex command-line tool from github.com/openai/codex, run codex once to sign in, and restart Flow.' },
  ollama: { costs: 'nothing', documents: 'never leave this computer',
            install: 'Install Ollama from ollama.com/download (it is free), start it, and press Check again.' },
};

/** Reading engines: the default reader, then every engine with its models. */
function pageEngines() {
  if (!ENGINE_SETTINGS) loadEngineSettings();
  if (!MODELS) loadModels();
  else if (!modelsTimer && Object.values(MODELS.pulls || {}).some((p) => !p.done)) {
    modelsTimer = setTimeout(loadModels, 1500);
  }
  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('div', { class: 'page-title' }, el('h1', {}, 'Reading engines')),
      el('p', { class: 'page-sub' },
        'An engine is how Flow reaches a reader: Claude Code, Codex, or Ollama on this computer. Each offers '
        + 'models, and the model is the reader. Flow computes the tax itself; the model only copies facts out '
        + 'of your papers. A return picks its engine and model under Returns.')),
    el('div', { class: 'page-actions' },
      el('button', { class: 'ghost', type: 'button',
                     onclick: () => { MODELS = null; ENGINE_SETTINGS = null; refresh().then(renderPanel); } },
         icon('refresh'), 'Check again')));
  if (!ENGINE_SETTINGS || !MODELS) {
    return [head, el('div', { class: 'card' }, el('div', { class: 'card-body muted' }, 'Looking for engines…'))];
  }

  const choices = ENGINE_SETTINGS.choices || {};
  const defaults = ENGINE_SETTINGS.defaults || {};
  const engines = (state.engines || []).filter((e) => e.selectable);
  const think = (choices.think || []).map((t) => ({ value: t.value, label: t.label }));
  const usedBy = (ref) => (state.profiles?.profiles || [])
    .filter((p) => canonicalEngine(p.settings?.engine || '') === ref).map((p) => p.name);
  const defaultRef = canonicalEngine(engineValue(['default_engine']));

  const field = (label, control, note) => el('div', { class: 'ret-field' },
    el('label', {}, label), control, note ? el('small', {}, note) : null);
  const minutes = (name) => field('Time limit, minutes',
    el('input', { type: 'number', min: '1', max: '600', step: '1', value: engineValue(['time_limits_minutes', name]),
                  oninput: (e) => setEngineDraft(['time_limits_minutes', name], e.target.value) }),
    `How long one reading may take before Flow stops it. Default ${defaults.time_limits_minutes?.[name] ?? 30}.`);

  // An Ollama model's own window or reasoning; "as shared" follows the
  // Ollama-wide value until the model is given its own.
  const shared = { num_ctx: engineValue(['ollama', 'num_ctx']), think: engineValue(['ollama', 'think']) };
  const sharedLabel = (key) => (key === 'num_ctx' ? `${Math.round((shared.num_ctx || 65536) / 1024)}k`
    : (think.find((t) => t.value === (shared.think === false || shared.think === undefined ? 'off' : shared.think)) || {}).label || 'Off');
  const modelPick = (name, key) => {
    const options = key === 'num_ctx'
      ? (choices.windows || []).map((w) => ({ value: String(w), label: `${Math.round(w / 1024)}k tokens` }))
      : think;
    const box = el('select', { onchange: (e) => setEngineDraft(['ollama', 'models', name, key], e.target.value) },
      el('option', { value: '' }, `As shared (${sharedLabel(key)})`),
      options.map((o) => el('option', { value: o.value }, o.label)));
    const own = engineValue(['ollama', 'models', name, key]);
    box.value = own === undefined || own === null ? '' : own === false ? 'off' : String(own);
    return el('label', { class: 'mdl-pick' }, el('span', {}, key === 'num_ctx' ? 'Window' : 'Reasoning'), box);
  };

  const installedInfo = (name) => (MODELS.installed || []).find((x) => x.name === name);

  /** One model of an engine: what it is, who uses it, its own settings. */
  const modelRow = (e, m) => {
    const users = usedBy(m.ref);
    const info = e.id === 'ollama' ? installedInfo(m.id) : null;
    const isDefault = defaultRef === m.ref;
    return el('div', { class: 'mdl-row' + (isDefault ? ' default' : '') },
      el('div', { class: 'mdl-row-h' },
        el('div', { class: 'mdl-row-t' },
          el('b', {}, m.label),
          el('span', { class: 'muted' }, info
            ? [info.family, info.parameters ? `${info.parameters} parameters` : null, gb(info.bytes)].filter(Boolean).join(' · ')
            : m.note)),
        isDefault ? chip('Default reader', 'ok') : null,
        users.length ? chip(`Used by ${users.join(', ')}`, 'line') : null),
      el('div', { class: 'mdl-row-f' },
        e.id === 'ollama' ? [modelPick(m.id, 'num_ctx'), modelPick(m.id, 'think')] : null,
        el('div', { class: 'mdl-row-acts' },
          isDefault || !e.available ? null : el('button', { class: 'ghost small', type: 'button',
            title: 'Every return that does not choose its own will read with this.',
            onclick: () => { setEngineDraft(['default_engine'], m.ref); renderPanel(); } }, 'Make default reader'),
          e.id === 'ollama' ? el('button', { class: 'ghost small', type: 'button', onclick: () => {
            if (confirm(`Remove ${m.id} from this computer?${users.length ? `\n\n${users.join(', ')} read with it and will go back to the default reader.` : ''}\n\nIt can be downloaded again at any time.`)) modelAction('remove', m.id);
          } }, 'Remove') : null,
          e.id === 'codex' && m.added ? el('button', { class: 'ghost small', type: 'button', onclick: () => {
            const left = (engineValue(['codex', 'models']) || []).filter((n) => n !== m.id);
            saveEngineSettings({ codex: { models: left } });
          } }, 'Remove') : null)));
  };

  /** Ways to add models, where an engine allows it. */
  const addModels = (e) => {
    if (e.id === 'ollama') return MODELS.running ? ollamaAdd(MODELS) : null;
    if (e.id === 'codex') {
      const box = el('input', { placeholder: 'a model name your Codex accepts, e.g. gpt-5-codex', spellcheck: 'false' });
      const add = () => {
        const name = box.value.trim();
        if (!name) return;
        saveEngineSettings({ codex: { models: [...(engineValue(['codex', 'models']) || []), name] } });
      };
      box.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') add(); });
      return el('div', { class: 'eng-sub' }, el('h4', {}, 'Add a model'),
        el('div', { class: 'mdl-custom' }, el('label', {}, 'Model name'), box,
          el('button', { class: 'ghost', type: 'button', onclick: add }, 'Add')),
        el('p', { class: 'muted', style: 'margin-top:8px' }, 'Codex is asked for this model by name; it must be one your plan offers.'));
    }
    return null;
  };

  /** One engine: whether it is here, what it costs, its shared settings, its models. */
  const engineCard = (e) => {
    const facts = ENGINE_FACTS[e.id] || {};
    const status = e.id === 'ollama'
      ? chip(MODELS.running ? `Running · ${MODELS.version || ''} · ${e.models.length} model(s)` : 'Not running', MODELS.running ? 'ok' : 'warn')
      : chip(e.available ? 'Ready' : 'Not found', e.available ? 'ok' : 'warn');
    return el('section', { class: 'card eng-card' },
      el('div', { class: 'eng-h' }, el('h2', {}, e.label), status),
      el('div', { class: 'eng-facts' },
        el('span', {}, el('b', {}, 'Costs'), ` ${facts.costs || ''}`),
        el('span', {}, el('b', {}, 'Your documents'), ` ${facts.documents || ''}`)),
      el('div', { class: 'eng-body' },
        el('div', { class: 'ret-grid' },
          minutes(e.id),
          e.id === 'ollama' ? field('Address', el('input', { value: engineValue(['ollama', 'host']) || '', spellcheck: 'false',
            oninput: (ev) => setEngineDraft(['ollama', 'host'], ev.target.value) }), 'Where Ollama listens. Change only if you moved it.') : null),
        (e.id === 'ollama' && !MODELS.running) || (e.id !== 'ollama' && !e.available)
          ? el('p', { class: 'muted' }, facts.install) : null,
        el('div', { class: 'eng-sub' },
          el('h4', {}, `Models (${e.models.length})`,
            el('small', {}, e.id === 'ollama' ? ' each installed model is a reader of its own' : ' the readers this engine offers')),
          e.models.length ? el('div', { class: 'mdl-rows' }, e.models.map((m) => modelRow(e, m)))
                          : el('p', { class: 'muted' }, e.id === 'ollama' ? 'No model yet. Add one below.' : 'None offered.')),
        addModels(e)));
  };

  const groups = new Map();
  (state.engineChoices || []).forEach((c) => {
    if (!groups.has(c.group)) groups.set(c.group, []);
    groups.get(c.group).push(c);
  });
  const defaultBox = el('select', { onchange: (ev) => { setEngineDraft(['default_engine'], ev.target.value); renderPanel(); } },
    [...groups.entries()].map(([group, list]) => el('optgroup', { label: group },
      list.map((c) => el('option', { value: c.value }, c.label + (c.available ? '' : ' (not found)'))))));
  defaultBox.value = defaultRef;

  return [head,
    el('section', { class: 'card eng-card' },
      el('div', { class: 'eng-h' }, el('h2', {}, 'Default reader')),
      el('div', { class: 'eng-body' }, el('div', { class: 'ret-grid' },
        field('Every return that does not choose its own reads with', defaultBox,
              'A return can still choose another engine and model under Returns › Reading engine.')))),
    engines.map(engineCard),
    el('div', { class: 'ret-save eng-save', id: 'eng-save', hidden: !Object.keys(ENGINE_DRAFT).length },
      el('span', {}, 'You have unsaved changes to the engines.'),
      el('button', { class: 'ghost', type: 'button', onclick: () => { ENGINE_DRAFT = {}; renderPanel(); } }, 'Discard'),
      el('button', { class: 'primary', type: 'button', onclick: () => saveEngineSettings(ENGINE_DRAFT) }, 'Save changes')),
    el('p', { class: 'muted eng-where' }, `Saved in ${ENGINE_SETTINGS.stored_at || 'your Flow folder'}, not in the program, so updating Flow never changes them.`),
  ];
}
