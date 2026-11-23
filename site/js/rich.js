// Tiny, safe text formatter for puzzle/reward text (no innerHTML).
//   blank line = new paragraph, ``` fences = copyable code, **bold**, `code`

export function rich(text) {
  const frag = document.createDocumentFragment();
  String(text).replace(/\r/g, '').split(/```[^\n]*\n([\s\S]*?)```/).forEach((chunk, i) => {
    if (i % 2) { frag.append(codeBlock(chunk.replace(/\n$/, ''))); return; }
    chunk.split(/\n{2,}/).forEach((par) => {
      par = par.replace(/^\n+|\n+$/g, '');
      if (!par) return;
      const p = document.createElement('p');
      par.split('\n').forEach((ln, n) => {
        if (n) p.append(document.createElement('br'));
        ln.split(/(\*\*[^*]+\*\*|`[^`]+`)/).forEach((tok) => {
          if (/^\*\*[^*]+\*\*$/.test(tok)) {
            const b = document.createElement('strong'); b.textContent = tok.slice(2, -2); p.append(b);
          } else if (/^`[^`]+`$/.test(tok)) {
            const c = document.createElement('code'); c.textContent = tok.slice(1, -1); p.append(c);
          } else if (tok) p.append(tok);
        });
      });
      frag.append(p);
    });
  });
  return frag;
}

function codeBlock(code) {
  const wrap = document.createElement('div');
  wrap.className = 'codewrap';
  const pre = document.createElement('pre');
  pre.textContent = code;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'copy';
  btn.textContent = 'copy';
  btn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(code); btn.textContent = 'copied'; }
    catch { btn.textContent = 'select + copy'; }
    setTimeout(() => { btn.textContent = 'copy'; }, 1500);
  });
  wrap.append(pre, btn);
  return wrap;
}
