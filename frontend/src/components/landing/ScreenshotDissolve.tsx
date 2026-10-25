import { useEffect, useRef, useState } from 'react';

export function ScreenshotDissolve({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previous = useRef(active);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (previous.current === active) return;
    previous.current = active;
    const canvas = canvasRef.current;
    const picture = canvas?.parentElement?.querySelector('img');
    const context = canvas?.getContext('2d');
    if (!canvas || !picture || !context || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setRunning(false); return; }
    let frame = 0, disposed = false;
    const ease = (value: number) => { const t = Math.max(0, Math.min(1, value)); return t * t * (3 - 2 * t); };
    const start = () => {
      const width = canvas.clientWidth, height = canvas.clientHeight;
      if (disposed || !picture.naturalWidth || !width || !height) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const columns = window.innerWidth <= 700 ? 16 : 22;
      const rows = Math.max(6, Math.round(columns * height / width));
      const cellW = width / columns, cellH = height / rows;
      const sx = -picture.offsetLeft / picture.offsetWidth * picture.naturalWidth;
      const sy = -picture.offsetTop / picture.offsetHeight * picture.naturalHeight;
      const sw = width / picture.offsetWidth * picture.naturalWidth;
      const sh = height / picture.offsetHeight * picture.naturalHeight;
      const glyphs = ['0', '1', '{', '}', '<', '>', '/', ';', '[]', '=>'];
      const started = performance.now();
      let last = 0;
      setRunning(true);
      const draw = (time: number) => {
        if (disposed) return;
        if (document.hidden) { setRunning(false); return; }
        if (time - last < 30) { frame = requestAnimationFrame(draw); return; }
        last = time;
        const progress = Math.min(1, (time - started) / 1250);
        const scatter = active ? 1 - ease((progress - .12) / .88) : ease(progress / .7);
        const code = ease((scatter - .04) / .45);
        context.clearRect(0, 0, width, height);
        context.textAlign = 'center'; context.textBaseline = 'middle';
        context.font = `${7 + scatter * 3}px ui-monospace, SFMono-Regular, Consolas, monospace`;
        for (let row = 0; row < rows; row++) {
          for (let column = 0; column < columns; column++) {
            const index = row * columns + column;
            const seed = (index * .61803398875) % 1;
            const angle = index * 2.39996323 + scatter * 3;
            const x = (column + .5) * cellW + Math.cos(angle) * scatter * width * (.12 + seed * .26);
            const y = (row + .5) * cellH + Math.sin(angle) * scatter * height * (.15 + seed * .3);
            if (code < 1) {
              const size = 1 - code * .65;
              context.globalAlpha = 1 - code;
              context.drawImage(picture, sx + column / columns * sw, sy + row / rows * sh, sw / columns, sh / rows,
                x - cellW * size / 2, y - cellH * size / 2, cellW * size + .5, cellH * size + .5);
            }
            if (code > 0) {
              context.globalAlpha = code * (.5 + seed * .5) * (1 - scatter * .2);
              context.fillStyle = index % 7 ? '#c4dcef' : '#9edaff';
              context.fillText(glyphs[(index + Math.floor(progress * 12)) % glyphs.length], x, y);
            }
          }
        }
        context.globalAlpha = 1;
        if (progress < 1) frame = requestAnimationFrame(draw);
        else { context.clearRect(0, 0, width, height); setRunning(false); }
      };
      frame = requestAnimationFrame(draw);
    };
    if (picture.complete) start();
    else picture.addEventListener('load', start, { once: true });
    return () => { disposed = true; cancelAnimationFrame(frame); picture.removeEventListener('load', start); };
  }, [active]);

  return <canvas ref={canvasRef} className="landing-dissolve" data-running={running} aria-hidden="true" />;
}
