import { useEffect, useRef, useState } from 'react';

export function LandingEntrance() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [phase, setPhase] = useState<'gather' | 'form' | 'reveal' | 'done'>(() =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'done' : 'gather');
  const active = phase !== 'done';

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!active || !canvas) return;
    const context = canvas.getContext('2d');
    if (!context) { setPhase('done'); return; }
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const samples = window.innerWidth <= 700 ? 34 : 65;
    const particles = Array.from({ length: samples * 8 }, (_, index) => ({
      u: (index % samples) / (samples - 1),
      arm: Math.floor(index / samples) * Math.PI / 4,
      escape: index * 2.39996323,
      radius: .7 + (Math.sin(index * 37.3) + 1) * .45,
      warm: index % 37 === 0,
    }));
    let width = 0, height = 0, frame = 0, elapsed = 0, previousTime = 0;
    let formed = false, revealed = false;
    let letters: { x: number; y: number }[] = [];
    let previous: { x: number; y: number }[] = [];
    const ease = (value: number) => {
      const t = Math.max(0, Math.min(1, value));
      return t * t * (3 - 2 * t);
    };
    const resize = () => {
      width = window.innerWidth; height = window.innerHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      previous = [];
      const mask = document.createElement('canvas');
      mask.width = width; mask.height = height;
      const ink = mask.getContext('2d');
      if (!ink) return;
      ink.fillStyle = '#fff'; ink.textBaseline = 'middle';
      canvas.closest('.um-landing')?.querySelectorAll<HTMLElement>('.landing-hero-statement > span').forEach(span => {
        const rect = span.getBoundingClientRect();
        const style = getComputedStyle(span);
        ink.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        let x = rect.left;
        for (const character of span.textContent || '') {
          ink.fillText(character, x, rect.top + rect.height / 2);
          x += ink.measureText(character).width + (parseFloat(style.letterSpacing) || 0);
        }
      });
      const pixels = ink.getImageData(0, 0, width, height).data;
      const points: typeof letters = [];
      for (let y = 0; y < height; y += 3) {
        for (let x = 0; x < width; x += 3) {
          if (pixels[(y * width + x) * 4 + 3] > 90) points.push({ x, y });
        }
      }
      const step = Math.max(1, Math.ceil(points.length / (width <= 700 ? 1000 : 1900)));
      letters = points.filter((_, index) => index % step === 0);
    };

    const draw = (time: number) => {
      if (!document.hidden) elapsed += previousTime ? Math.min(time - previousTime, 48) : 0;
      previousTime = time;
      const gather = ease(elapsed / 1250);
      const letterform = letters.length ? ease((elapsed - 1050) / 650) : 0;
      const burst = Math.max(0, Math.min(1, (elapsed - 2100) / 1100));
      const spread = ease(burst);
      const opacity = ease(elapsed / 180) * (1 - ease((elapsed - 2850) / 600));
      const cover = 1 - ease((elapsed - 2050) / 650);
      const scale = Math.min(width * .47, height * .58);
      const centerX = width * .5, centerY = height * .48;
      const seconds = elapsed / 1000;
      context.clearRect(0, 0, width, height);
      context.fillStyle = `rgba(8, 11, 15, ${cover})`;
      context.fillRect(0, 0, width, height);

      const glow = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, scale * .28);
      glow.addColorStop(0, `rgba(177, 218, 252, ${gather * (1 - spread) * .22})`);
      glow.addColorStop(1, 'rgba(177, 218, 252, 0)');
      context.fillStyle = glow; context.fillRect(0, 0, width, height);

      const points = particles.map((particle, index) => {
        const angle = particle.arm + particle.u * 14 - seconds * (3.2 + gather * 8);
        const radius = scale * (.04 + Math.pow(particle.u, 1.25) * .96) * (1 - gather * .94);
        const depth = Math.sin(angle);
        const perspective = 1 + depth * .12;
        const bend = Math.sin(particle.u * 2.9 + seconds * .65) * scale * .16 * (1 - gather);
        const x = (Math.cos(angle) * radius + bend) * perspective;
        const y = ((.45 - particle.u) * height * .58 * (1 - gather * .98) + depth * radius * .2) * perspective;
        const escapeAngle = particle.escape + seconds * .7 + spread * Math.PI;
        const distance = Math.hypot(width, height) * spread * (.65 + particle.u * .6);
        const letter = letters[Math.floor(index / particles.length * letters.length)];
        const gatheredX = x * (1 - letterform) + ((letter?.x ?? centerX) - centerX) * letterform;
        const gatheredY = y * (1 - letterform) + ((letter?.y ?? centerY) - centerY) * letterform;
        return {
          x: centerX + gatheredX * (1 - spread) + Math.cos(escapeAngle) * distance,
          y: centerY + gatheredY * (1 - spread) + Math.sin(escapeAngle) * distance * .85,
          depth,
        };
      });

      points.forEach((point, index) => {
        const particle = particles[index];
        const alpha = opacity * (.35 + (point.depth + 1) * .25);
        const last = previous[index];
        if (last) {
          context.beginPath(); context.moveTo(last.x, last.y); context.lineTo(point.x, point.y);
          context.strokeStyle = `rgba(192, 213, 231, ${alpha * .25 * (1 - letterform * .9)})`;
          context.lineWidth = .65; context.stroke();
        }
        if (index % samples) {
          const neighbor = points[index - 1];
          context.beginPath(); context.moveTo(neighbor.x, neighbor.y); context.lineTo(point.x, point.y);
          context.strokeStyle = `rgba(192, 213, 231, ${opacity * .23 * (1 - burst) ** 3 * (1 - letterform) ** 2})`;
          context.lineWidth = .65; context.stroke();
        }
        if (index >= samples && index % 5 === 0 && burst < .5) {
          const neighbor = points[index - samples];
          context.beginPath(); context.moveTo(neighbor.x, neighbor.y); context.lineTo(point.x, point.y);
          context.strokeStyle = `rgba(192, 213, 231, ${opacity * .08 * (1 - burst) * (1 - letterform) ** 2})`;
          context.lineWidth = .45; context.stroke();
        }
        context.beginPath(); context.arc(point.x, point.y, particle.radius, 0, Math.PI * 2);
        context.fillStyle = particle.warm ? `rgba(174, 220, 255, ${alpha})` : `rgba(223, 234, 244, ${alpha})`;
        context.fill();
      });
      const letterOpacity = ease((elapsed - 1450) / 300) * (1 - ease((elapsed - 2350) / 550));
      if (letterOpacity > 0) {
        context.fillStyle = `rgba(218, 234, 247, ${letterOpacity * .82})`;
        context.beginPath();
        letters.forEach((letter, index) => {
          const angle = index * 2.39996323;
          const distance = Math.hypot(width, height) * spread;
          const x = letter.x + Math.cos(angle) * distance;
          const y = letter.y + Math.sin(angle) * distance;
          context.moveTo(x + .8, y); context.arc(x, y, .8, 0, Math.PI * 2);
        });
        context.fill();
      }
      previous = points;
      if (!formed && elapsed >= 1550) { formed = true; setPhase('form'); }
      if (!revealed && elapsed >= 2050) { revealed = true; setPhase('reveal'); }
      if (elapsed < 3450) frame = requestAnimationFrame(draw);
      else setPhase('done');
    };
    const reduceMotion = () => { if (preference.matches) setPhase('done'); };
    resize(); frame = requestAnimationFrame(draw);
    window.addEventListener('resize', resize);
    preference.addEventListener('change', reduceMotion);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      preference.removeEventListener('change', reduceMotion);
    };
  }, [active]);

  return active ? <canvas ref={canvasRef} className="landing-entrance" data-phase={phase} aria-hidden="true" /> : null;
}
