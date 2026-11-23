import { normalize, b64d, pad2 } from './shared.js';

const te = new TextEncoder();
const td = new TextDecoder();

export const cryptoAvailable = () => !!(window.crypto && crypto.subtle);

// Try to open a door. Returns the reward ({iter, title, text, physical, items[]})
// or null if the answer is wrong. Throws on network problems.
export async function unlockDoor(day, guess) {
  const norm = normalize(guess);
  if (!norm) return null;
  const tag = pad2(day);

  const res = await fetch(`d/${tag}.json`, { cache: 'no-cache' });
  if (!res.ok) throw new Error('door data missing');
  const meta = await res.json();

  // answer -> key-encryption key (slow on purpose: it makes guessing expensive)
  const material = await crypto.subtle.importKey('raw', te.encode(norm), 'PBKDF2', false, ['deriveKey']);
  const kek = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt: b64d(meta.salt), iterations: meta.iter },
    material, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);

  // each accepted answer has its own wrapped copy of the content key
  let dekRaw = null;
  for (const w of meta.wraps) {
    try {
      dekRaw = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: b64d(w.iv), additionalData: te.encode(`leo-advent|${tag}|wrap`) },
        kek, b64d(w.ct));
      break;
    } catch { /* not this one */ }
  }
  if (!dekRaw) return null;

  const dek = await crypto.subtle.importKey('raw', dekRaw, 'AES-GCM', false, ['decrypt']);
  const bin = await fetch(`d/${meta.bin}`);
  if (!bin.ok) throw new Error('reward data missing');
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: b64d(meta.iv), additionalData: te.encode(`leo-advent|${tag}|body`) },
    dek, await bin.arrayBuffer());
  return { iter: meta.iter, ...parseContainer(plain) };
}

// [4 bytes manifest length][manifest JSON][file bytes, in manifest order]
function parseContainer(buf) {
  const len = new DataView(buf).getUint32(0);
  const manifest = JSON.parse(td.decode(new Uint8Array(buf, 4, len)));
  let off = 4 + len;
  const items = manifest.items.map((it) => {
    const blob = new Blob([buf.slice(off, off + it.length)], { type: it.mime });
    off += it.length;
    return { ...it, url: URL.createObjectURL(blob) };
  });
  return { ...manifest, items };
}
