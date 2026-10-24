import { useEffect, useRef } from 'react';

type Mode = 'plan' | 'understand' | 'practice';
type Point = [number, number, number];
const TAU = Math.PI * 2;
const MODES: Mode[] = ['plan', 'understand', 'practice'];

function geometry(u: number, v: number, mode: number): Point {
  if (mode === 0) {
    const radius = 1.06 + .35 * Math.cos(v);
    return [radius * Math.cos(u), .56 * Math.sin(v), radius * Math.sin(u)];
  }
  if (mode === 1) {
    const x = (u / Math.PI - 1) * 1.42;
    return [x, .53 * Math.sin(u * 1.25 + v * .7) + .23 * Math.cos(v), .83 * Math.cos(v) + .2 * Math.sin(u)];
  }
  const latitude = .08 + v / TAU * (Math.PI - .16);
  const radius = 1.12 + .12 * Math.sin(u * 3 + latitude * 2);
  return [radius * Math.cos(u) * Math.sin(latitude), 1.08 * Math.cos(latitude), radius * Math.sin(u) * Math.sin(latitude)];
}

/** A transparent canvas that morphs between the three tool views. */
export function IntelligenceField({ mode }: { mode: Mode }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const modeRef = useRef(MODES.indexOf(mode));
  const pulseRef = useRef(0);
  const redrawRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const next = MODES.indexOf(mode);
    if (next !== modeRef.current) pulseRef.current = 1;
    modeRef.current = next;
    redrawRef.current?.();
  }, [mode]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    const parent = canvas?.parentElement;
    if (!canvas || !context || !parent) return;
    const pointerSurface = parent.parentElement || parent;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reduced = preference.matches;
    let visible = true;
    let width = 0;
    let height = 0;
    let raf = 0;
    let lastFrame = 0;
    let phase = .4;
    const weights: number[] = MODES.map((_, index) => index === modeRef.current ? 1 : 0);
    const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };

    const schedule = () => {
      if (!raf && visible && !document.hidden) raf = requestAnimationFrame(draw);
    };
    const project = (u: number, v: number): Point => {
      const point: Point = [0, 0, 0];
      weights.forEach((weight, index) => {
        if (weight < .001) return;
        const shape = geometry(u, v, index);
        shape.forEach((value, axis) => { point[axis] += value * weight; });
      });
      const turn = -.48 + phase * .085 + pointer.x * .18;
      const tilt = .46 + pointer.y * .15;
      const x = point[0] * Math.cos(turn) - point[2] * Math.sin(turn);
      const depth = point[0] * Math.sin(turn) + point[2] * Math.cos(turn);
      const y = point[1] * Math.cos(tilt) - depth * Math.sin(tilt);
      const z = point[1] * Math.sin(tilt) + depth * Math.cos(tilt);
      const mobile = window.innerWidth <= 900;
      const scale = Math.min(width * (mobile ? .32 : .245), height * .38);
      const perspective = 4 / (4 - z * .35);
      return [width * (mobile ? .5 : .66) + x * scale * perspective,
        height * .48 + y * scale * perspective, z];
    };

    function draw(time: number) {
      raf = 0;
      if (!visible || document.hidden || !width || !height) return;
      if (!reduced && time - lastFrame < 32) { schedule(); return; }
      const elapsed = Math.min(time - lastFrame, 64);
      lastFrame = time;
      const pulse = reduced ? 0 : pulseRef.current;
      pulseRef.current = Math.max(0, pulse - elapsed / 1450);
      if (!reduced) phase += elapsed / 1000;
      weights.forEach((weight, index) => {
        const target = index === modeRef.current ? 1 : 0;
        weights[index] = reduced ? target : weight + (target - weight) * .065;
      });
      pointer.x += ((reduced ? 0 : pointer.targetX) - pointer.x) * .06;
      pointer.y += ((reduced ? 0 : pointer.targetY) - pointer.y) * .06;
      context!.clearRect(0, 0, width, height);

      // Each contour retains its depth, rather than flattening into a uniform grid.
      const contours: { points: Point[]; depth: number; cross: boolean }[] = [];
      for (let line = 0; line < 28; line++) {
        const cross = line >= 20;
        const points = Array.from({ length: 73 }, (_, sample) => project(
          cross ? (line - 20) / 8 * TAU : sample / 72 * TAU,
          cross ? sample / 72 * TAU : line / 20 * TAU,
        ));
        contours.push({ points, depth: points.reduce((sum, point) => sum + point[2], 0) / points.length, cross });
      }
      contours.sort((a, b) => a.depth - b.depth).forEach(({ points, depth, cross }) => {
        context!.beginPath();
        points.forEach(([x, y], index) => { if (index) context!.lineTo(x, y); else context!.moveTo(x, y); });
        context!.strokeStyle = `rgba(191, 211, 229, ${Math.max(.12, .28 + depth * .12) * (cross ? .66 : 1)})`;
        context!.lineWidth = cross ? .6 : .8;
        context!.stroke();
      });

      if (pulse > 0) {
        const front = (1 - pulse) * contours.length;
        context!.save(); context!.shadowColor = '#c0e3ff'; context!.shadowBlur = 12;
        contours.forEach(({ points }, index) => {
          const intensity = Math.max(0, 1 - Math.abs(index - front) / 3) * Math.sin(pulse * Math.PI);
          if (intensity < .02) return;
          context!.beginPath();
          points.forEach(([x, y], point) => { if (point) context!.lineTo(x, y); else context!.moveTo(x, y); });
          context!.strokeStyle = `rgba(215, 239, 255, ${intensity})`;
          context!.lineWidth = 1.8; context!.stroke();
        });
        context!.restore();
      }

      // Only a compressed, fading portion of the live geometry reaches the floor.
      const floor = height * .77;
      const reflection = context!.createLinearGradient(0, floor, 0, floor + height * .18);
      reflection.addColorStop(0, 'rgba(149, 197, 234, .085)');
      reflection.addColorStop(1, 'rgba(149, 197, 234, 0)');
      context!.save(); context!.beginPath(); context!.rect(0, floor, width, height * .18); context!.clip();
      contours.forEach(({ points, cross }) => {
        context!.beginPath();
        points.forEach(([x, y], index) => {
          const reflectedY = floor + (floor - y) * .42;
          if (index) context!.lineTo(x, reflectedY); else context!.moveTo(x, reflectedY);
        });
        context!.strokeStyle = reflection; context!.globalAlpha = cross ? .6 : 1;
        context!.lineWidth = .7; context!.stroke();
      });
      context!.restore();

      // A single traveling path and sparse light nodes reveal the surface topology.
      const pathV = .7 + weights[1] * .8 + weights[2] * 1.2;
      const head = (phase * .24) % TAU;
      for (let segment = 0; segment < 15; segment++) {
        const start = project(head - segment * .035, pathV);
        const end = project(head - (segment + 1) * .035, pathV);
        context!.beginPath(); context!.moveTo(start[0], start[1]); context!.lineTo(end[0], end[1]);
        context!.strokeStyle = `rgba(176, 220, 255, ${(1 - segment / 15) * .68})`;
        context!.lineWidth = 1.25; context!.stroke();
      }
      // White specular light travels along the surface, independent of the ice-blue route.
      context!.save(); context!.shadowColor = 'rgba(255, 255, 255, .7)'; context!.shadowBlur = 7;
      for (let segment = 0; segment < 40; segment++) {
        const start = project(head * 1.3 - segment * .04, pathV + 1.5);
        const end = project(head * 1.3 - (segment + 1) * .04, pathV + 1.5);
        context!.beginPath(); context!.moveTo(start[0], start[1]); context!.lineTo(end[0], end[1]);
        context!.strokeStyle = `rgba(255, 255, 255, ${Math.sin(segment / 40 * Math.PI) * .9})`;
        context!.lineWidth = 1.6; context!.stroke();
      }
      context!.restore();
      [0, 2.1, 4.3].forEach((offset, index) => {
        const [x, y] = project(head + offset, pathV + index * .8);
        const energy = pulse * Math.max(0, Math.cos((1 - pulse) * TAU - offset));
        context!.save(); context!.shadowColor = '#b8e4ff'; context!.shadowBlur = energy * 18;
        context!.beginPath(); context!.arc(x, y, (index ? 2 : 3.2) + energy * 3, 0, TAU);
        context!.fillStyle = index ? '#c3d2df' : '#bae0ff'; context!.fill();
        context!.strokeStyle = '#ffffff'; context!.lineWidth = 1.5; context!.stroke();
        context!.restore();
      });
      if (!reduced) schedule();
    }

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      width = rect.width; height = rect.height;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0); schedule();
    };
    const move = (event: PointerEvent) => {
      const rect = parent.getBoundingClientRect();
      pointer.targetX = (event.clientX - rect.left) / Math.max(1, rect.width) - .5;
      pointer.targetY = (event.clientY - rect.top) / Math.max(1, rect.height) - .5;
    };
    const leave = () => { pointer.targetX = 0; pointer.targetY = 0; };
    const visibility = () => {
      if (document.hidden || !visible) { cancelAnimationFrame(raf); raf = 0; }
      else { lastFrame = 0; schedule(); }
    };
    const motion = () => { reduced = preference.matches; phase = .4; schedule(); };
    const resizeObserver = new ResizeObserver(resize);
    const intersectionObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; visibility(); });
    resizeObserver.observe(parent); intersectionObserver.observe(canvas);
    pointerSurface.addEventListener('pointermove', move); pointerSurface.addEventListener('pointerleave', leave);
    document.addEventListener('visibilitychange', visibility); preference.addEventListener('change', motion);
    redrawRef.current = schedule; resize();
    return () => {
      cancelAnimationFrame(raf); redrawRef.current = null;
      resizeObserver.disconnect(); intersectionObserver.disconnect();
      pointerSurface.removeEventListener('pointermove', move); pointerSurface.removeEventListener('pointerleave', leave);
      document.removeEventListener('visibilitychange', visibility); preference.removeEventListener('change', motion);
    };
  }, []);

  return <canvas ref={canvasRef} className="landing-intelligence-field" aria-hidden="true"
    style={{ width: '100%', height: '100%', display: 'block', pointerEvents: 'none' }} />;
}

export default IntelligenceField;
