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
    let cosTurn = 1, sinTurn = 0, cosTilt = 1, sinTilt = 0, scale = 0, centerX = 0;
    const weights: number[] = MODES.map((_, index) => index === modeRef.current ? 1 : 0);
    const pointer = { x: 0, y: 0, targetX: 0, targetY: 0, localX: 0, localY: 0, force: 0, targetForce: 0, velocity: 0 };

    const schedule = () => {
      if (!raf && visible && !document.hidden) raf = requestAnimationFrame(draw);
    };
    const project = (u: number, v: number): Point => {
      let px = 0, py = 0, pz = 0;
      for (let index = 0; index < weights.length; index++) {
        const weight = weights[index];
        if (weight < .001) continue;
        const shape = geometry(u, v, index);
        px += shape[0] * weight; py += shape[1] * weight; pz += shape[2] * weight;
      }
      const x = px * cosTurn - pz * sinTurn;
      const depth = px * sinTurn + pz * cosTurn;
      const y = py * cosTilt - depth * sinTilt;
      const z = py * sinTilt + depth * cosTilt;
      const perspective = 4 / (4 - z * .35);
      const screenX = centerX + x * scale * perspective;
      const screenY = height * .48 + y * scale * perspective;
      const dx = pointer.localX - screenX, dy = pointer.localY - screenY;
      const radius = Math.min(width, height) * .35;
      const attraction = pointer.force > .001 ? Math.exp(-(dx * dx + dy * dy) / (radius * radius)) * pointer.force * .32 : 0;
      return [screenX + dx * attraction, screenY + dy * attraction, z];
    };

    function draw(time: number) {
      raf = 0;
      if (!visible || document.hidden || !width || !height) return;
      const elapsed = Math.min(time - lastFrame, 64);
      lastFrame = time;
      const pulse = reduced ? 0 : pulseRef.current;
      pulseRef.current = Math.max(0, pulse - elapsed / 1450);
      if (!reduced) phase += elapsed / 1000;
      const blend = 1 - Math.exp(-elapsed / 300);
      weights.forEach((weight, index) => {
        const target = index === modeRef.current ? 1 : 0;
        weights[index] = reduced ? target : weight + (target - weight) * blend;
      });
      pointer.x += ((reduced ? 0 : pointer.targetX) - pointer.x) * blend;
      pointer.y += ((reduced ? 0 : pointer.targetY) - pointer.y) * blend;
      const step = elapsed / 32;
      pointer.velocity = (pointer.velocity + ((reduced ? 0 : pointer.targetForce) - pointer.force) * .08 * step) * Math.pow(.78, step);
      pointer.force = reduced ? 0 : pointer.force + pointer.velocity * step;
      const turn = -.48 + phase * .085 + pointer.x * .18, tilt = .46 + pointer.y * .15;
      cosTurn = Math.cos(turn); sinTurn = Math.sin(turn); cosTilt = Math.cos(tilt); sinTilt = Math.sin(tilt);
      const mobile = window.innerWidth <= 900;
      scale = Math.min(width * (mobile ? .32 : .245), height * .38); centerX = width * (mobile ? .5 : .66);
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

      if (!reduced) {
        const glyphs = ['0', '1', '{', '}', '/', '<', '>', '=>'];
        context!.save(); context!.font = `${window.innerWidth <= 700 ? 9 : 11}px ui-monospace, SFMono-Regular, Consolas, monospace`;
        context!.textAlign = 'center'; context!.textBaseline = 'middle';
        for (let stream = 0; stream < 7; stream++) {
          const u = phase * (.45 + stream * .025) + stream * .87;
          const v = (stream * 3 + 1) / 20 * TAU;
          for (let tail = 4; tail >= 0; tail--) {
            const point = project(u - tail * .11, v), next = project(u - tail * .11 + .025, v);
            context!.save(); context!.translate(point[0], point[1]);
            context!.rotate(Math.atan2(next[1] - point[1], next[0] - point[0]));
            context!.fillStyle = `rgba(193, 225, 249, ${(1 - tail / 5) * Math.max(.3, .85 + point[2] * .12)})`;
            context!.fillText(glyphs[(stream + tail + Math.floor(phase * 2)) % glyphs.length], 0, 0);
            context!.restore();
          }
        }
        context!.restore();
      }

      if (pulse > 0) {
        const front = (1 - pulse) * contours.length;
        context!.save();
        contours.forEach(({ points }, index) => {
          const intensity = Math.max(0, 1 - Math.abs(index - front) / 3) * Math.sin(pulse * Math.PI);
          if (intensity < .02) return;
          context!.beginPath();
          points.forEach(([x, y], point) => { if (point) context!.lineTo(x, y); else context!.moveTo(x, y); });
          context!.strokeStyle = `rgba(192, 227, 255, ${intensity * .16})`;
          context!.lineWidth = 5; context!.stroke();
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
      context!.save();
      const highlight = Array.from({ length: 41 }, (_, segment) => project(head * 1.3 - segment * .04, pathV + 1.5));
      const shine = context!.createLinearGradient(highlight[0][0], highlight[0][1], highlight[40][0], highlight[40][1]);
      shine.addColorStop(0, '#ffffff00'); shine.addColorStop(.5, '#ffffffe6'); shine.addColorStop(1, '#ffffff00');
      context!.beginPath();
      highlight.forEach(([x, y], index) => { if (index) context!.lineTo(x, y); else context!.moveTo(x, y); });
      context!.strokeStyle = shine; context!.globalAlpha = .16; context!.lineWidth = 4; context!.stroke();
      context!.globalAlpha = 1; context!.lineWidth = 1.6; context!.stroke();
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
      if (event.pointerType !== 'mouse') return;
      const rect = parent.getBoundingClientRect();
      pointer.localX = event.clientX - rect.left; pointer.localY = event.clientY - rect.top;
      pointer.targetForce = 1;
      pointer.targetX = (event.clientX - rect.left) / Math.max(1, rect.width) - .5;
      pointer.targetY = (event.clientY - rect.top) / Math.max(1, rect.height) - .5;
    };
    const leave = () => { pointer.targetX = 0; pointer.targetY = 0; pointer.targetForce = 0; };
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
