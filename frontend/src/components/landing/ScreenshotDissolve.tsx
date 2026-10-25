import { useEffect, useRef, useState } from 'react';

export function ScreenshotDissolve({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previous = useRef(active);
  const cacheRef = useRef<{ width: number; height: number; texture: HTMLCanvasElement; atlas: HTMLCanvasElement } | null>(null);
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
      const ratio = Math.min(window.devicePixelRatio || 1, 1.25);
      if (canvas.width !== Math.round(width * ratio)) canvas.width = Math.round(width * ratio);
      if (canvas.height !== Math.round(height * ratio)) canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const glyphs = ['0', '1', '{', '}', '<', '>', '/', ';', '[]', '=>'];
      let cached = cacheRef.current;
      if (!cached || cached.width !== canvas.width || cached.height !== canvas.height) {
        const texture = document.createElement('canvas');
        texture.width = canvas.width; texture.height = canvas.height;
        texture.getContext('2d', { alpha: false })!.drawImage(picture,
          -picture.offsetLeft / picture.offsetWidth * picture.naturalWidth,
          -picture.offsetTop / picture.offsetHeight * picture.naturalHeight,
          width / picture.offsetWidth * picture.naturalWidth,
          height / picture.offsetHeight * picture.naturalHeight, 0, 0, texture.width, texture.height);
        const atlas = document.createElement('canvas');
        atlas.width = 20 * glyphs.length * 2; atlas.height = 32;
        const ink = atlas.getContext('2d')!;
        ink.scale(2, 2); ink.font = '10px ui-monospace, SFMono-Regular, Consolas, monospace';
        ink.textAlign = 'center'; ink.textBaseline = 'middle'; ink.fillStyle = '#c4e3fa';
        glyphs.forEach((glyph, index) => ink.fillText(glyph, index * 20 + 10, 8));
        cached = { width: canvas.width, height: canvas.height, texture, atlas };
        cacheRef.current = cached;
      }
      const { texture, atlas } = cached;
      const columns = window.innerWidth <= 700 ? 12 : 18;
      const rows = Math.max(6, Math.round(columns * height / width));
      const cellW = width / columns, cellH = height / rows;
      const particles = Array.from({ length: columns * rows }, (_, index) => {
        const seed = (index * .61803398875) % 1;
        return { column: index % columns, row: Math.floor(index / columns), seed,
          cos: Math.cos(index * 2.39996323), sin: Math.sin(index * 2.39996323) };
      });
      const started = performance.now();
      setRunning(true);
      const draw = (time: number) => {
        if (disposed) return;
        if (document.hidden) { picture.style.removeProperty('opacity'); setRunning(false); return; }
        const progress = Math.min(1, (time - started) / 900);
        const scatter = active ? 1 - ease(progress) : ease(progress / .8);
        const code = ease((scatter - .04) / .45);
        const turnCos = Math.cos(scatter * 3), turnSin = Math.sin(scatter * 3);
        picture.style.opacity = (1 - code).toFixed(3);
        context.clearRect(0, 0, width, height);
        particles.forEach(({ column, row, seed, cos, sin }, index) => {
          const x = (column + .5) * cellW + (cos * turnCos - sin * turnSin) * scatter * width * (.12 + seed * .26);
          const y = (row + .5) * cellH + (sin * turnCos + cos * turnSin) * scatter * height * (.15 + seed * .3);
          if (code > .02 && code < .995) {
            const size = 1 - code * .65;
            context.globalAlpha = (1 - code) * Math.sin(scatter * Math.PI);
            context.drawImage(texture, column / columns * texture.width, row / rows * texture.height,
              texture.width / columns, texture.height / rows,
              x - cellW * size / 2, y - cellH * size / 2, cellW * size + .5, cellH * size + .5);
          }
          if (code > 0) {
            const size = .8 + scatter * .3;
            context.globalAlpha = code * (.5 + seed * .5) * (1 - scatter * .2);
            context.drawImage(atlas, (index + Math.floor(progress * 12)) % glyphs.length * 40, 0, 40, 32,
              x - 10 * size, y - 8 * size, 20 * size, 16 * size);
          }
        });
        context.globalAlpha = 1;
        if (progress < 1) frame = requestAnimationFrame(draw);
        else { picture.style.removeProperty('opacity'); context.clearRect(0, 0, width, height); setRunning(false); }
      };
      draw(started);
    };
    if (picture.complete) start();
    else picture.addEventListener('load', start, { once: true });
    return () => { disposed = true; cancelAnimationFrame(frame); picture.style.removeProperty('opacity'); picture.removeEventListener('load', start); };
  }, [active]);

  return <canvas ref={canvasRef} className="landing-dissolve" data-running={running} aria-hidden="true" />;
}
