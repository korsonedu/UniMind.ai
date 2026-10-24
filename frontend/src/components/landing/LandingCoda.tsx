import { useEffect, useRef, useState } from 'react';

export function LandingCoda() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const logoRef = useRef<HTMLImageElement>(null);
  const [settled, setSettled] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (settled) return;
    const canvas = canvasRef.current, logo = logoRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !logo || !context) return;
    let width = 0, height = 0, frame = 0, elapsed = 0, lastTime = 0, visible = false;
    let shown = false;
    const glyphs = ['0', '1', '{', '}', '<', '>', '/', ';', ':', '=', '()', '[]', '=>', '&&'];
    let points: { x: number; y: number }[] = [];
    const schedule = () => { if (!frame && visible && points.length && !document.hidden) frame = requestAnimationFrame(draw); };

    function draw(time: number) {
      frame = 0;
      if (!visible || document.hidden) { lastTime = 0; return; }
      elapsed += lastTime ? Math.min(48, time - lastTime) : 0;
      lastTime = time;
      const progress = Math.max(0, Math.min(1, (elapsed - 200) / 1400));
      const gather = 1 - (1 - progress) ** 3;
      const spread = Math.max(0, Math.min(1, (elapsed - 1850) / 750)) ** 2;
      context!.clearRect(0, 0, width, height);
      const positions = points.map((point, index) => {
        const angle = index * 2.39996323 + elapsed * .004;
        const orbit = .2 + (index % 17) / 21;
        return {
          x: width / 2 + (point.x - width / 2) * gather + Math.cos(angle) * width * orbit * (.5 * (1 - gather) + spread),
          y: height / 2 + (point.y - height / 2) * gather + Math.sin(angle) * height * orbit * (.5 * (1 - gather) + spread),
        };
      });
      context!.strokeStyle = `rgba(182, 215, 240, ${(1 - progress) * .2})`;
      context!.lineWidth = .6; context!.beginPath();
      positions.forEach((point, index) => {
        const next = positions[index + 1];
        if (index % 7 || !next || Math.hypot(next.x - point.x, next.y - point.y) > 65) return;
        context!.moveTo(point.x, point.y); context!.lineTo(next.x, next.y);
      });
      context!.stroke();
      context!.textAlign = 'center'; context!.textBaseline = 'middle';
      context!.font = `${8 - gather * 4 + spread * 3}px ui-monospace, SFMono-Regular, Consolas, monospace`;
      context!.fillStyle = `rgba(218, 235, 248, ${(.4 + gather * .55) * (1 - spread)})`;
      positions.forEach(({ x, y }, index) => context!.fillText(glyphs[(index + (gather < .95 ? Math.floor(elapsed / 100) : 0)) % glyphs.length], x, y));
      if (!shown && elapsed >= 1800) { shown = true; setRevealed(true); }
      if (elapsed < 2600) schedule();
      else setSettled(true);
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width; height = rect.height;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      if (!logo.naturalWidth) return;
      const mark = document.createElement('canvas');
      mark.width = Math.round(Math.min(250, width * .52));
      mark.height = Math.round(mark.width * logo.naturalHeight / logo.naturalWidth);
      const ink = mark.getContext('2d');
      if (!ink) return;
      ink.drawImage(logo, 0, 0, mark.width, mark.height);
      const pixels = ink.getImageData(0, 0, mark.width, mark.height).data;
      const samples: typeof points = [];
      for (let y = 0; y < mark.height; y += 3) {
        for (let x = 0; x < mark.width; x += 3) {
          const i = (y * mark.width + x) * 4;
          if (pixels[i + 3] > 80 && (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3 < 140) samples.push({ x: (width - mark.width) / 2 + x, y: (height - mark.height) / 2 + y });
        }
      }
      const step = Math.max(1, Math.ceil(samples.length / 450));
      points = samples.filter((_, index) => index % step === 0);
      schedule();
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (!visible) { cancelAnimationFrame(frame); frame = 0; lastTime = 0; }
      else schedule();
    }, { threshold: .4 });
    const resizeObserver = new ResizeObserver(resize);
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const motion = () => { if (preference.matches) setSettled(true); };
    observer.observe(canvas); resizeObserver.observe(canvas);
    logo.addEventListener('load', resize);
    document.addEventListener('visibilitychange', schedule);
    preference.addEventListener('change', motion);
    resize();
    return () => {
      cancelAnimationFrame(frame); observer.disconnect(); resizeObserver.disconnect();
      logo.removeEventListener('load', resize);
      document.removeEventListener('visibilitychange', schedule);
      preference.removeEventListener('change', motion);
    };
  }, [settled]);

  return <div className={`landing-coda${revealed ? ' is-revealed' : ''}${settled ? ' is-settled' : ''}`} aria-hidden="true">
    <canvas ref={canvasRef} />
    <img ref={logoRef} src="/Unimind_logo_wide.png" alt="" width="250" height="62" />
  </div>;
}
