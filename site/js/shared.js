// Must behave exactly like normalize() in build.py.
export const normalize = (s) =>
  String(s).normalize('NFKD').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

export const b64d = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const pad2 = (n) => String(n).padStart(2, '0');

export function ordinal(n) {
  const v = n % 100;
  if (v >= 11 && v <= 13) return n + 'th';
  return n + (['th', 'st', 'nd', 'rd'][n % 10] || 'th');
}

export function pick(list, avoid) {
  let x;
  do { x = list[Math.floor(Math.random() * list.length)]; } while (list.length > 1 && x === avoid);
  return x;
}
