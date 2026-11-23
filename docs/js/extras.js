// Interactive puzzle parts: signal lamp (door 21), role gate (door 16), guard chat (door 19).
import { sleep } from './shared.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// ---------------------------------------------------------------- lamp
// sig.pattern: [[1|0, milliseconds], ...]; plays in a loop while isAlive() is true.
export function mountSignal(sig, isAlive) {
  const box = el('div', 'signal');
  const lamp = el('div', 'lamp');
  lamp.setAttribute('role', 'img');
  lamp.setAttribute('aria-label', 'signal lamp');
  const play = el('button', 'btn', 'play');
  play.type = 'button';
  const label = el('label', 'soundopt');
  const sound = el('input'); sound.type = 'checkbox';
  label.append(sound, ' sound');
  box.append(lamp, play, label);

  let running = false, audio = null, gain = null;

  function setLamp(on) {
    lamp.classList.toggle('on', on);
    if (gain) gain.gain.value = on && sound.checked ? 0.12 : 0;
  }
  async function loop() {
    while (running && isAlive()) {
      for (const [on, ms] of sig.pattern) {
        if (!running || !isAlive()) break;
        setLamp(on === 1);
        await sleep(ms);
      }
      setLamp(false);
      if (running) await sleep(2500);
    }
    running = false; setLamp(false); play.textContent = 'play';
  }
  play.addEventListener('click', () => {
    if (running) { running = false; return; }
    try {
      if (!audio) {
        audio = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audio.createOscillator(); osc.frequency.value = 660;
        gain = audio.createGain(); gain.gain.value = 0;
        osc.connect(gain).connect(audio.destination); osc.start();
      }
      audio.resume();
    } catch { /* no sound: the lamp still works */ }
    running = true; play.textContent = 'stop'; loop();
  });
  return box;
}

// ---------------------------------------------------------------- role gate
function getCookie(name) {
  const m = document.cookie.split('; ').find((c) => c.startsWith(encodeURIComponent(name) + '='));
  return m ? decodeURIComponent(m.slice(m.indexOf('=') + 1)) : '';
}
function getStore(name) { try { return localStorage.getItem(name) || ''; } catch { return ''; } }

// Start as a guest, unless the visitor has already changed the role.
export function initRole(gate) {
  if (!getCookie(gate.name)) {
    try { document.cookie = `${encodeURIComponent(gate.name)}=${encodeURIComponent(gate.start)}; path=/; max-age=2592000; SameSite=Lax`; } catch { /* ignore */ }
  }
  if (!getStore(gate.name)) {
    try { localStorage.setItem(gate.name, gate.start); } catch { /* ignore */ }
  }
}

// Every value that differs from the starting role (cookie first, then storage).
export function changedRoles(gate) {
  return [...new Set([getCookie(gate.name), getStore(gate.name)])].filter((v) => v && v !== gate.start);
}

// ---------------------------------------------------------------- guard chat
export async function askGuard(url, messages) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  });
  if (res.status === 429) throw new Error('rate');
  if (!res.ok) throw new Error('http');
  const data = await res.json();
  return String(data.reply || '');
}
