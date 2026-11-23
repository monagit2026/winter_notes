import { normalize, sleep, pad2, ordinal, pick } from './shared.js';
import { unlockDoor, cryptoAvailable } from './crypto.js';
import { syncClock, doorStatus, secondsUntilDoor, formatCountdown, doorDateLabel, zoned, trueNow } from './clock.js';
import { rich } from './rich.js';
import { startSnow } from './snow.js';
import { mountSignal, initRole, changedRoles, askGuard } from './extras.js';

const $ = (s) => document.querySelector(s);
const screen = $('#screen');
const form = $('#prompt');
const input = $('#cmd');
const ps1 = $('#ps1');
const HOME_PS1 = 'leo@advent:~$';
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const finePointer = matchMedia('(pointer: fine)').matches;

// ---------------------------------------------------------------- progress
const KEY = 'leo-advent-v1';
let progress = { solved: {}, hints: {}, booted: false, theme: 'green', snow: true };
try { Object.assign(progress, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch { /* storage blocked: stay in memory */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(progress)); } catch { /* ignore */ } };

// ---------------------------------------------------------------- state
let cfg, doors = new Map(), snow, view = { name: 'home' }, busy = false;
const history = []; let histPos = 0;
const DAYS = Array.from({ length: 24 }, (_, i) => i + 1);

// ---------------------------------------------------------------- helpers
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function line(text, cls) {
  const e = el('div', 'ln' + (cls ? ' ' + cls : ''), text);
  screen.append(e);
  screen.scrollTop = screen.scrollHeight;
  return e;
}
const clear = () => screen.replaceChildren();
function setPrompt(label, ask) { ps1.textContent = label; form.classList.toggle('ask', !!ask); }
function btn(label, fn) { const b = el('button', 'btn', label); b.type = 'button'; b.addEventListener('click', fn); return b; }
function focusInput() { if (finePointer) input.focus(); }

function state(day) {
  const d = doors.get(day);
  if (!d) return { kind: 'empty' };
  const lock = doorStatus(day, cfg);
  if (lock !== 'open') return { kind: 'locked', lock, d };
  return { kind: progress.solved[day] ? 'solved' : 'open', d };
}

// ---------------------------------------------------------------- boot
const TREE = [
  '      *      ',
  '     /o\\     ',
  '    /@  \\    ',
  '   /  o  \\   ',
  '  /o   @  \\  ',
  ' /  @  o   \\ ',
  '/o   @   o  \\',
  '/_____ _____\\',
  '     |||     ',
];

function treeEl() {
  const pre = el('pre', 'tree');
  pre.setAttribute('aria-hidden', 'true');
  for (const ch of TREE.join('\n')) {
    if (ch === '*') pre.append(Object.assign(el('span', 'star'), { textContent: ch }));
    else if (ch === 'o') pre.append(Object.assign(el('span', 'ball'), { textContent: ch }));
    else if (ch === '@') pre.append(Object.assign(el('span', 'gold'), { textContent: ch }));
    else pre.append(ch);
  }
  return pre;
}

let skipBoot = false;
const wait = (ms) => (skipBoot ? Promise.resolve() : sleep(ms));

async function bootSequence() {
  clear();
  setPrompt('', false);
  form.hidden = true;
  const skip = () => { skipBoot = true; };
  addEventListener('keydown', skip); addEventListener('pointerdown', skip);
  const steps = [
    ['Initialising LEO-OS v30.0 ...', null, 500],
    ['Loading festive kernel modules', 'ok', 350],
    ['Mounting /doors (24 volumes, all encrypted)', 'ok', 350],
    ['Calibrating snow engine', 'ok', 300],
    ['Checking security module', 'WEAK', 400],
    ['Scanning user ...', null, 450],
    ['  former software engineer detected', null, 250],
    ['  threat level: shenanigans', 'warn', 400],
  ];
  if (!skipBoot) line('(tap or press any key to skip)', 'dim');
  for (const [text, status, delay] of steps) {
    const l = line(text);
    await wait(delay);
    if (status) {
      const s = el('span', status === 'ok' ? 'accent' : 'err', status === 'ok' ? '  [ OK ]' : `  [ ${status.toUpperCase()} ]`);
      l.append(s);
    }
  }
  line('');
  line('Welcome, Leo.', 'accent');
  await wait(900);
  removeEventListener('keydown', skip); removeEventListener('pointerdown', skip);
  form.hidden = false;
}

// ---------------------------------------------------------------- home
function doorCell(day) {
  const s = state(day);
  const b = el('button', 'door s-' + s.kind);
  b.type = 'button';
  b.dataset.day = day;
  const tag = { open: 'NEW', solved: 'DONE', locked: 'LOCKED', empty: 'EMPTY' }[s.kind];
  const name = s.kind === 'locked' || s.kind === 'empty' ? '??????' : s.d.title;
  b.append(el('span', 'num', pad2(day)), el('span', 'tag', tag), el('span', 'name', name), el('span', 'date', doorDateLabel(day, cfg)));
  b.setAttribute('aria-label', `Door ${day}, ${tag.toLowerCase()}`);
  b.addEventListener('click', () => openDoor(day));
  return b;
}

function renderGrid() {
  const g = $('#grid');
  if (!g) return;
  g.replaceChildren(...DAYS.map(doorCell));
  const done = DAYS.filter((d) => progress.solved[d]).length;
  $('#count').textContent = `decrypted: ${done}/24`;
}

function showHome() {
  view = { name: 'home' };
  clear();
  setPrompt(HOME_PS1, false);
  const hero = el('div', 'hero');
  const info = el('div');
  info.append(el('h1', null, 'LEO-OS v30.0'), el('div', 'dim', 'ADVENT TERMINAL // 24 encrypted doors'));
  const meta = el('div', 'meta');
  const countdown = el('div'); countdown.id = 'cd';
  const count = el('div'); count.id = 'count';
  meta.append(countdown, count);
  info.append(meta);
  hero.append(treeEl(), info);
  screen.append(hero);

  const z = zoned(trueNow(), cfg.timezone);
  if (z.m === cfg.month && z.d === 19) {
    screen.append(el('div', 'birthday', '*** HAPPY BIRTHDAY LEO!  v30.0 RELEASED ***'));
  }
  line('$ ls /doors', 'echo');
  const grid = el('div', 'grid'); grid.id = 'grid';
  screen.append(grid);
  renderGrid();
  line('tap a door, or type: open 5   (help for more)', 'dim');
  updateCountdown();
  screen.scrollTop = 0;
}

function nextLocked() {
  return DAYS.find((d) => doors.has(d) ? state(d).kind === 'locked' : doorStatus(d, cfg) !== 'open');
}

function updateCountdown() {
  const c = $('#cd');
  if (!c) return;
  const next = nextLocked();
  c.textContent = next
    ? `door ${pad2(next)} opens in ${formatCountdown(secondsUntilDoor(next, cfg))}`
    : 'all doors are open';
}

let lastSig = '';
function tick() {
  const sig = DAYS.map((d) => state(d).kind).join('');
  if (view.name === 'home' && sig !== lastSig && lastSig) renderGrid();
  lastSig = sig;
  if (view.name === 'home') updateCountdown();
}

// ---------------------------------------------------------------- doors
function openDoor(day) {
  if (busy) return;
  const s = state(day);
  if (s.kind === 'empty') {
    if (view.name !== 'home') showHome();
    return line(`door ${day}: volume not mounted. (no content yet)`, 'err');
  }
  if (s.kind === 'locked') {
    if (view.name !== 'home') showHome();
    if (s.lock === 'cheat') {
      return line(`ACCESS DENIED. Nice try, hacker. Door ${day} opens on the ${ordinal(day)}. 😉`, 'err');
    }
    return line(`door ${day} is locked until ${doorDateLabel(day, cfg)}, 00:00 Berlin time. Patience.`, 'err');
  }
  showDoor(day);
}

function setCookie({ name, value }) {
  try { document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; path=/; max-age=2592000; SameSite=Lax`; } catch { /* ignore */ }
}

function clueNode(f) {
  const ext = f.name.split('.').pop().toLowerCase();
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return Object.assign(el('img'), { src: f.url, alt: f.name });
  if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) return Object.assign(el('audio'), { src: f.url, controls: true });
  const a = el('a', null, '> ' + f.name);
  a.href = f.url; a.target = '_blank'; a.rel = 'noopener';
  const p = el('div'); p.append(a);
  return p;
}

async function showDoor(day) {
  const d = doors.get(day);
  const mine = view = { name: 'door', day, guard: d.guard || null, roleGate: d.role_gate || null, mode: 'answer', chat: [], tried: new Set() };
  const solved = progress.solved[day];
  clear();
  (d.cookies || []).forEach(setCookie);

  const head = el('div', 'dhead');
  head.append(el('span', 'dnum', `DOOR ${pad2(day)}`), el('span', 'dtitle', d.title), el('span', 'ddate', doorDateLabel(day, cfg)));
  screen.append(head);
  line(`$ cat /doors/${pad2(day)}/${d.title}`, 'echo');
  const body = el('div', 'body'); body.append(rich(d.puzzle));
  screen.append(body);
  if (d.files.length) {
    const clues = el('div', 'clues');
    d.files.forEach((f) => clues.append(clueNode(f)));
    screen.append(clues);
  }
  if (d.signal) screen.append(mountSignal(d.signal, () => view === mine));
  const shown = Math.min(progress.hints[day] || 0, d.hints.length);
  for (let i = 0; i < shown; i++) line(`hint ${i + 1}/${d.hints.length}: ${d.hints[i]}`, 'hintline');

  const bar = el('div', 'actions');
  bar.append(btn('< back', showHome));
  if (!solved) {
    bar.append(btn('hint', giveHint));
    if (d.guard) bar.append(btn('enter password', () => setMode('answer')));
    if (d.role_gate) bar.append(btn('refresh permissions', () => checkRole(mine, d, true)));
  }
  screen.append(bar);

  if (solved) {
    setPrompt(HOME_PS1, false);
    const st = line('restoring decrypted session ...', 'dim');
    try {
      const payload = await unlockDoor(day, solved);
      if (view !== mine) return;
      st.remove();
      if (payload) return renderReward(payload);
    } catch { /* fall through */ }
    if (view !== mine) return;
    st.remove();
    delete progress.solved[day]; save();
    line('stored credentials rejected. Please log in again.', 'err');
  }
  if (!d.ready) line('This door is still under construction (no answer set yet).', 'err');

  if (d.guard) {
    restoreChat(mine, d);
    setMode('chat');
    line('talk to the guard below. /pw <password> or "enter password" to try a password. /hint  /back', 'dim');
  } else if (d.role_gate) {
    initRole(d.role_gate);
    setPrompt('guest@advent:~$', false);
    line(`current session: role=${d.role_gate.start}. type /refresh after changing something.  /hint  /back`, 'dim');
    checkRole(mine, d, false);
    const timer = setInterval(() => {
      if (view !== mine || view.solved) clearInterval(timer);
      else checkRole(mine, d, false);
    }, 1500);
  } else {
    setPrompt(d.prompt, true);
    line('enter the answer below.  /hint  /back', 'dim');
  }
  focusInput();
}

// ---- door 16: role gate
let checking = false;
async function checkRole(mine, d, manual) {
  if (view !== mine || view.solved || checking) return;
  const roles = changedRoles(d.role_gate);
  if (manual && !roles.length) line(`permissions unchanged: role=${d.role_gate.start}`, 'dim');
  for (const role of roles) {
    if (view.tried.has(role) && !manual) continue;
    view.tried.add(role);
    checking = true;
    try {
      const payload = await unlockDoor(d.day, role);
      if (view !== mine) return;
      if (payload) { await grant(d.day, role, payload); return; }
      line(`role=${role}: not authorised. (the server is not impressed)`, 'err');
    } catch { line('connection error. Check your internet and try again.', 'err'); }
    finally { checking = false; }
  }
}

// ---- door 19: guard chat
function setMode(mode) {
  if (!view.guard || view.solved) return;
  view.mode = mode;
  const d = doors.get(view.day);
  setPrompt(mode === 'chat' ? 'you>' : d.prompt, true);
  if (mode === 'answer') line('type the password. /chat goes back to the guard.', 'dim');
  focusInput();
}

const chatKey = (day) => `leo-advent-chat-${day}`;
function restoreChat(mine, d) {
  try { mine.chat = JSON.parse(sessionStorage.getItem(chatKey(d.day)) || '[]'); } catch { mine.chat = []; }
  if (!mine.chat.length) { if (d.guard.intro) line(`${d.guard.name}: ${d.guard.intro}`, 'accent'); return; }
  mine.chat.forEach((m) => line(m.role === 'user' ? `you> ${m.content}` : `${d.guard.name}: ${m.content}`, m.role === 'user' ? 'echo' : 'accent'));
}

async function chat(text) {
  const mine = view;
  const d = doors.get(view.day);
  if (text.length > 300) return line('message too long (300 characters max). The elf has no patience.', 'err');
  if (!d.guard.url) return line('the guard is not connected yet.', 'err');
  line(`you> ${text}`, 'echo');
  busy = true; input.readOnly = true;
  const wait = line(`${d.guard.name} is typing ...`, 'dim');
  try {
    mine.chat.push({ role: 'user', content: text });
    const reply = await askGuard(d.guard.url, mine.chat.slice(-40));
    wait.remove();
    if (view !== mine) return;
    mine.chat.push({ role: 'assistant', content: reply });
    try { sessionStorage.setItem(chatKey(d.day), JSON.stringify(mine.chat.slice(-40))); } catch { /* ignore */ }
    line(`${d.guard.name}: ${reply}`, 'accent');
  } catch (e) {
    wait.remove();
    mine.chat.pop();
    line(e.message === 'rate'
      ? 'Too many messages! The elf needs a breather. Try again in a few minutes.'
      : 'The elf is on a coffee break (connection error). Try again in a moment.', 'err');
  } finally {
    busy = false; input.readOnly = false;
    focusInput();
  }
}

function giveHint() {
  if (view.name !== 'door') return line('open a door first.', 'err');
  const d = doors.get(view.day);
  if (progress.solved[view.day]) return line('already solved, no hint needed.', 'dim');
  const n = progress.hints[view.day] || 0;
  if (!d.hints.length) return line('no hints for this door. You are on your own, hacker.', 'hintline');
  if (n >= d.hints.length) return line('no more hints. The elves are out of ideas.', 'hintline');
  progress.hints[view.day] = n + 1; save();
  line(`hint ${n + 1}/${d.hints.length}: ${d.hints[n]}`, 'hintline');
}

const WRONG = [
  'ACCESS DENIED. The elves are laughing.',
  'Wrong. Even Rudolph could do better.',
  'Incorrect. This incident will be reported to Santa.',
  'Nope. Have you tried turning it off and on again?',
  'Permission denied (publickey,gingerbread).',
  'Hash mismatch. Try again, hacker.',
  '403: Forbidden by order of the Grinch.',
  'Authentication failed. The snow is judging you.',
  'Close. (It was not close.)',
];
let lastWrong = '';

async function grant(day, text, payload) {
  const mine = view;
  line(`deriving key (PBKDF2-SHA256 x ${payload.iter.toLocaleString('en-US')}) ... ok`, 'dim');
  await sleep(reduceMotion ? 0 : 350);
  line('unwrapping content key ... ok', 'dim');
  await sleep(reduceMotion ? 0 : 300);
  line('decrypting payload (AES-256-GCM) ... ok', 'dim');
  await sleep(reduceMotion ? 0 : 400);
  progress.solved[day] = normalize(text); save();
  if (view !== mine) return;
  renderReward(payload);
}

async function submitAnswer(text) {
  const day = view.day;
  const d = doors.get(day);
  line(`${ps1.textContent} ${text}`, 'echo');
  if (!d.ready) return line('nothing to decrypt yet: this door has no answer set.', 'err');
  busy = true; input.readOnly = true;
  const st = line('verifying ...', 'dim');
  try {
    const payload = await unlockDoor(day, text);
    st.remove();
    if (!payload) {
      lastWrong = pick(WRONG, lastWrong);
      line(lastWrong, 'err');
      form.classList.remove('shake'); void form.offsetWidth; form.classList.add('shake');
      if (view.guard) setMode('chat');
      return;
    }
    await grant(day, text, payload);
  } catch {
    st.remove();
    line('connection error. Check your internet and try again.', 'err');
  } finally {
    busy = false; input.readOnly = false;
  }
}

function renderReward(payload) {
  view.solved = true;
  setPrompt(HOME_PS1, false);
  const box = el('div', 'reward');
  box.append(el('div', 'granted', '>> ACCESS GRANTED'));
  if (payload.title) box.append(el('h2', null, payload.title));
  if (payload.physical) {
    const p = el('div', 'physical');
    p.append(el('strong', null, '🎁 PHYSICAL ITEM DETECTED'), rich(payload.physical));
    box.append(p);
  }
  if (payload.text) { const t = el('div', 'body'); t.append(rich(payload.text)); box.append(t); }
  for (const it of payload.items) {
    let node;
    if (it.kind === 'image') {
      node = el('a'); node.href = it.url; node.target = '_blank'; node.rel = 'noopener';
      node.append(Object.assign(el('img'), { src: it.url, alt: it.caption || it.name }));
    } else if (it.kind === 'audio') node = Object.assign(el('audio'), { src: it.url, controls: true });
    else if (it.kind === 'video') node = Object.assign(el('video'), { src: it.url, controls: true, playsInline: true });
    else { node = el('a', null, '> ' + it.name); node.href = it.url; node.download = it.name; }
    box.append(node);
    if (it.caption) box.append(el('div', 'caption', it.caption));
  }
  const bar = el('div', 'actions'); bar.append(btn('< back to doors', showHome));
  box.append(bar);
  screen.append(box);
  box.scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' });
}

// ---------------------------------------------------------------- commands
const HELP = [
  'ls                 list the doors',
  'open <1-24>        open a door (or just tap it)',
  'status             how far you are',
  'theme green|amber  change the colours',
  'snow on|off        toggle the snow',
  'boot               replay the boot sequence',
  'clear              clear the screen',
  'In a door: type the answer. /hint for a hint, /back to leave.',
  'With the guard: just chat. /pw <password> tries a password.',
];

async function command(text) {
  const [cmd, ...args] = text.trim().split(/\s+/);
  const c = (cmd || '').toLowerCase();
  if (!c) return;
  switch (c) {
    case 'ls': case 'back': case 'exit': case 'cd': case 'home':
      if (c === 'cd' && args[0] && args[0] !== '..' && args[0] !== '/') return openDoor(parseInt(args[0], 10));
      return showHome();
    case 'open': case 'cat': {
      const n = parseInt(args[0], 10);
      if (!(n >= 1 && n <= 24)) return line('usage: open <1-24>', 'err');
      return openDoor(n);
    }
    case 'hint': return giveHint();
    case 'pw': case 'password': case 'unlock':
      if (view.name !== 'door' || view.solved) return line('open a door first.', 'err');
      if (args.length) return submitAnswer(args.join(' '));
      return view.guard ? setMode('answer') : line('just type the answer.', 'dim');
    case 'chat': return view.guard && !view.solved ? setMode('chat') : line('nobody to chat with here.', 'dim');
    case 'refresh':
      return view.roleGate && !view.solved ? checkRole(view, doors.get(view.day), true) : line('nothing to refresh here.', 'dim');
    case 'help': case '?': HELP.forEach((h) => line(h, 'dim')); return;
    case 'clear': return view.name === 'door' ? showDoor(view.day) : showHome();
    case 'status': {
      const done = DAYS.filter((d) => progress.solved[d]);
      line(`decrypted ${done.length}/24: ${done.join(', ') || 'none yet'}`);
      updateCountdown();
      const next = nextLocked();
      line(next ? `next door: ${pad2(next)} in ${formatCountdown(secondsUntilDoor(next, cfg))}` : 'all doors are open.');
      return;
    }
    case 'theme': {
      const t = (args[0] || '').toLowerCase();
      if (t !== 'green' && t !== 'amber') return line('usage: theme green|amber', 'err');
      progress.theme = t; save(); applyTheme();
      return line(`theme: ${t}`, 'dim');
    }
    case 'snow': {
      const v = (args[0] || '').toLowerCase();
      if (v !== 'on' && v !== 'off') return line('usage: snow on|off', 'err');
      progress.snow = v === 'on'; save(); snow.setEnabled(progress.snow);
      return line(`snow: ${v}`, 'dim');
    }
    case 'boot': skipBoot = false; await bootSequence(); return showHome();
    case 'whoami': return line('leo. 30 years old. Allegedly.');
    case 'sudo': return line('leo is not in the sudoers file. This incident will be reported to Santa.', 'err');
    case 'rm': return line('nice try. The snow engine is not amused.', 'err');
    case 'ssh': case 'nmap': case 'hack': return line('The elves have a firewall. It is made of gingerbread, but still.', 'dim');
    default: line(`${c}: command not found. Try 'help'.`, 'err');
  }
}

async function handle(raw) {
  const text = raw.trim();
  if (!text || busy) return;
  if (view.name === 'door' && !view.solved) {
    if (text.startsWith('/')) return command(text.slice(1));
    if (view.roleGate) { line(`${ps1.textContent} ${text}`, 'echo'); return command(text); }
    if (view.guard && view.mode === 'chat') return chat(text);
    return submitAnswer(text);
  }
  line(`${HOME_PS1} ${text}`, 'echo');
  history.push(text); histPos = history.length;
  return command(text);
}


// ---------------------------------------------------------------- setup
function applyTheme() {
  document.documentElement.dataset.theme = progress.theme;
  snow?.refreshColor();
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const v = input.value;
  input.value = '';
  handle(v);
});
input.addEventListener('keydown', (e) => {
  if ((view.name === 'door' && !view.solved) || !history.length) return;
  if (e.key === 'ArrowUp') { histPos = Math.max(0, histPos - 1); input.value = history[histPos] || ''; e.preventDefault(); }
  if (e.key === 'ArrowDown') { histPos = Math.min(history.length, histPos + 1); input.value = history[histPos] || ''; e.preventDefault(); }
});
screen.addEventListener('click', (e) => {
  if (!getSelection().toString() && !e.target.closest('button, a, audio, video')) focusInput();
});

// keep the prompt above the on-screen keyboard (iOS)
if (window.visualViewport) {
  const fit = () => {
    document.documentElement.style.setProperty('--vvh', visualViewport.height + 'px');
    if (visualViewport.scale === 1) scrollTo(0, 0);
  };
  visualViewport.addEventListener('resize', fit);
  fit();
}

async function main() {
  if (!cryptoAvailable()) {
    line('This page needs a secure connection (https) to decrypt doors.', 'err');
    form.hidden = true;
    return;
  }
  try {
    const [c, list] = await Promise.all([
      fetch('config.json', { cache: 'no-cache' }).then((r) => r.json()),
      fetch('doors.json', { cache: 'no-cache' }).then((r) => r.json()),
      syncClock(),
    ]).then(([c, l]) => [c, l]);
    cfg = c;
    list.forEach((d) => doors.set(d.day, d));
  } catch {
    line('could not load the calendar. Check your connection and reload.', 'err');
    return;
  }
  snow = startSnow($('#snow'));
  snow.setEnabled(progress.snow);
  applyTheme();
  if (!progress.booted) { await bootSequence(); progress.booted = true; save(); }
  showHome();
  setInterval(tick, 1000);
}

main();
