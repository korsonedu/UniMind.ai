import { useEffect, useRef } from 'react';

export function CheckInFireworks({ burst }: { burst: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!burst || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * scale;
    canvas.height = height * scale;
    context.scale(scale, scale);
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--um-color-accent').trim() || '#4F5FA6';
    const particles = Array.from({ length: 72 }, (_, index) => {
      const group = Math.floor(index / 24);
      const angle = (index % 24) * Math.PI / 12;
      const speed = 70 + Math.random() * 60;
      return { x: width * [.3, .7, .5][group], y: height * [.42, .36, .5][group], vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, delay: group * 170, color: index % 3 === 0 ? '#D5B46C' : accent };
    });
    let frame = 0;
    let start: number | undefined;
    const draw = (time: number) => {
      start ??= time;
      const elapsed = time - start;
      context.clearRect(0, 0, width, height);
      for (const particle of particles) {
        const age = (elapsed - particle.delay) / 1000;
        if (age < 0 || age > 1.15) continue;
        context.globalAlpha = Math.max(0, 1 - age / 1.15);
        context.fillStyle = particle.color;
        context.beginPath();
        context.arc(particle.x + particle.vx * age, particle.y + particle.vy * age + 75 * age * age, 1.8, 0, Math.PI * 2);
        context.fill();
      }
      if (elapsed < 1500) frame = requestAnimationFrame(draw);
      else context.clearRect(0, 0, width, height);
    };
    frame = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(frame); context.clearRect(0, 0, width, height); };
  }, [burst]);
  return <canvas ref={canvasRef} className="um-checkin-fireworks" aria-hidden="true" />;
}
