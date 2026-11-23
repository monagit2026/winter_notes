// Falling snow made of ASCII characters, drawn on a canvas behind the terminal.

const CHARS = ['*', '.', '+', "'", '*', '.'];

export function startSnow(canvas) {
  const ctx = canvas.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w = 0, h = 0, flakes = [], color = '#39ff6a', on = true, last = 0;

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.min(70, Math.floor((w * h) / 16000));
    flakes = Array.from({ length: count }, () => spawn(true));
    if (still) draw();
  }

  function spawn(anywhere) {
    return {
      x: Math.random() * w, y: anywhere ? Math.random() * h : -20,
      speed: 18 + Math.random() * 30, size: 10 + Math.random() * 10,
      phase: Math.random() * 6.28, sway: 8 + Math.random() * 16,
      ch: CHARS[Math.floor(Math.random() * CHARS.length)],
    };
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    if (!on) return;
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.35;
    for (const f of flakes) {
      ctx.font = `${f.size}px ui-monospace, Menlo, monospace`;
      ctx.fillText(f.ch, f.x + Math.sin(f.phase) * f.sway, f.y);
    }
  }

  function frame(t) {
    const dt = Math.min(0.05, (t - last) / 1000 || 0);
    last = t;
    if (on) {
      flakes.forEach((f, i) => {
        f.y += f.speed * dt; f.phase += dt * 0.8;
        if (f.y > h + 20) flakes[i] = spawn(false);
      });
      draw();
    }
    requestAnimationFrame(frame);
  }

  window.addEventListener('resize', resize);
  resize();
  if (!still) requestAnimationFrame(frame);

  return {
    setEnabled(v) { on = v; draw(); },
    refreshColor() { color = getComputedStyle(document.documentElement).getPropertyValue('--fg').trim() || color; draw(); },
  };
}
