// Door dates. The lock is cosmetic (a clock can be faked); the real protection
// is the encryption. We still ask the server what time it is, so a faked device
// clock gets the "nice try" easter egg instead of a door.

// Server time at the moment we asked, plus time elapsed on the monotonic
// performance clock (which changing the device clock cannot move).
let base = null; // { server, perf }


export async function syncClock() {
  try {
    const p0 = performance.now();
    const r = await fetch('config.json', { method: 'HEAD', cache: 'no-store' });
    const p1 = performance.now();
    const header = r.headers.get('date');
    if (header) base = { server: Date.parse(header) + 500, perf: (p0 + p1) / 2 };
  } catch { /* offline: fall back to the device clock */ }
}

export function trueNow() {
  return base ? base.server + (performance.now() - base.perf) : Date.now();
}

const formatters = {};
export function zoned(ms, tz) {
  const f = formatters[tz] || (formatters[tz] = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz, weekday: 'short', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }));
  const o = {};
  for (const p of f.formatToParts(ms)) o[p.type] = p.value;
  return { y: +o.year, m: +o.month, d: +o.day, h: +o.hour, mi: +o.minute, s: +o.second, wd: o.weekday };
}

const ymd = (ms, tz) => { const z = zoned(ms, tz); return z.y * 10000 + z.m * 100 + z.d; };

// 'open' | 'locked' | 'cheat' (the device clock says open, the server says no)
export function doorStatus(day, cfg) {
  const target = cfg.year * 10000 + cfg.month * 100 + day;
  if (ymd(trueNow(), cfg.timezone) >= target) return 'open';
  if (ymd(Date.now(), cfg.timezone) >= target) return 'cheat';
  return 'locked';
}

export function secondsUntilDoor(day, cfg) {
  const now = zoned(trueNow(), cfg.timezone);
  const days = Math.round((Date.UTC(cfg.year, cfg.month - 1, day) - Date.UTC(now.y, now.m - 1, now.d)) / 864e5);
  return Math.max(0, days * 86400 - (now.h * 3600 + now.mi * 60 + now.s));
}

export function formatCountdown(sec) {
  const d = Math.floor(sec / 86400);
  const rest = sec % 86400;
  const hms = [Math.floor(rest / 3600), Math.floor((rest % 3600) / 60), rest % 60]
    .map((n) => String(n).padStart(2, '0')).join(':');
  return d ? `${d}d ${hms}` : hms;
}

export function doorDateLabel(day, cfg) {
  const wd = new Date(Date.UTC(cfg.year, cfg.month - 1, day))
    .toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' });
  const mon = new Date(Date.UTC(cfg.year, cfg.month - 1, day))
    .toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' });
  return `${wd} ${String(day).padStart(2, '0')} ${mon}`;
}
