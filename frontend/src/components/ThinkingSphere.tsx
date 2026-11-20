import { useEffect, useRef } from 'react';

type Point = readonly [number, number, number];
type Mesh = ReturnType<typeof buildMesh>;

const tau = 2 * Math.PI;
const golden = (1 + Math.sqrt(5)) / 2;
const camera = 4.6;
const cosPitch = Math.cos(.18);
const sinPitch = Math.sin(.18);
const palettes = {
  light: {
    shade: [40, 53, 106], sun: [68, 93, 182], edge: '#6173b8', route: '#516cbf',
    pulse: '#c5692c', core: '#d48045', tip: '#d85b10'
  },
  dark: {
    shade: [80, 95, 157], sun: [186, 205, 255], edge: '#8498e6', route: '#759cfc',
    pulse: '#ed984c', core: '#e6ae6e', tip: '#ffb55d'
  }
};
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const rgbMix = (a: number[], b: number[], amount: number) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * amount)).join(',')})`;
const vertices: Point[] = [
  [-1, golden, 0], [1, golden, 0], [-1, -golden, 0], [1, -golden, 0],
  [0, -1, golden], [0, 1, golden], [0, -1, -golden], [0, 1, -golden],
  [golden, 0, -1], [golden, 0, 1], [-golden, 0, -1], [-golden, 0, 1]
];
const faces = [
  [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
  [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
  [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
  [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]
];

function buildMesh() {
  const divisions = 2;
  const points: Point[] = [];
  const ids = new Map<string, number>();
  const edges = new Map<string, [number, number]>();
  const neighbors: number[][] = [];
  const connect = (a: number, b: number) => {
    const key = Math.min(a, b) + ':' + Math.max(a, b);
    if (edges.has(key)) return;
    edges.set(key, [a, b]);
    neighbors[a].push(b);
    neighbors[b].push(a);
  };

  for (const [a, b, c] of faces) {
    const grid: number[][] = [];
    for (let i = 0; i <= divisions; i++) {
      grid[i] = [];
      for (let j = 0; j <= divisions - i; j++) {
        const weighted = vertices[a].map((v, k) =>
          (divisions - i - j) * v + i * vertices[b][k] + j * vertices[c][k]
        );
        const norm = Math.hypot(...weighted);
        const point: Point = [weighted[0] / norm, weighted[1] / norm, weighted[2] / norm];
        const key = point.map(v => Math.round(v * 1e6)).join(',');
        let id = ids.get(key);
        if (id === undefined) {
          id = points.length;
          ids.set(key, id);
          neighbors.push([]);
          points.push(point);
        }
        grid[i][j] = id;
        if (j > 0) connect(id, grid[i][j - 1]);
        if (i > 0) {
          connect(id, grid[i - 1][j]);
          connect(id, grid[i - 1][j + 1]);
        }
      }
    }
  }
  return { points, edges: [...edges.values()], neighbors };
}

function nearest(points: Point[], vector: Point) {
  let best = -Infinity;
  let closest = 0;
  points.forEach(([x, y, z], index) => {
    const score = x * vector[0] + y * vector[1] + z * vector[2];
    if (score <= best) return;
    best = score;
    closest = index;
  });
  return closest;
}

function surfaceRoute(mesh: Mesh, from: Point, to: Point) {
  const start = nearest(mesh.points, from);
  const target = nearest(mesh.points, to);
  const queue = [start];
  const parent = new Map([[start, -1]]);
  for (const current of queue) {
    if (current === target) break;
    for (const next of mesh.neighbors[current]) {
      if (parent.has(next)) continue;
      parent.set(next, current);
      queue.push(next);
    }
  }
  const path: Point[] = [];
  for (let current = target; current !== -1; current = parent.get(current) ?? -1) {
    path.push(mesh.points[current]);
  }
  return path.reverse();
}

function buildLanes(mesh: Mesh) {
  const coreIn = mesh.points[nearest(mesh.points, [-.89, -.22, -.52])];
  const coreOut = mesh.points[nearest(mesh.points, [.81, .29, .57])];
  const routes: Point[][] = [
    surfaceRoute(mesh, [-.81, -.54, .22], [.78, .47, .55]),
    surfaceRoute(mesh, [.29, -.84, -.66], [-.46, .68, .60]),
    [coreIn, [-.41, -.18, -.33], [-.02, .03, -.12], [.41, .20, .26], coreOut]
  ];
  return routes.map(path => {
    const distances = [0];
    for (let i = 1; i < path.length; i++) {
      const length = Math.hypot(...path[i].map((value, axis) => value - path[i - 1][axis]));
      distances.push(distances[i - 1] + length);
    }
    return { path, distances };
  });
}

function position(lane: { path: Point[]; distances: number[] }, t: number): Point {
  const { path, distances } = lane;
  const length = clamp(t) * distances[distances.length - 1];
  const index = distances.findIndex((value, i) => i > 0 && value >= length);
  const a = path[index - 1];
  const b = path[index];
  const part = (length - distances[index - 1]) / (distances[index] - distances[index - 1]);
  return [a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part, a[2] + (b[2] - a[2]) * part];
}

const mesh = buildMesh();
const lanes = buildLanes(mesh);

function drawSphere(ctx: CanvasRenderingContext2D, half: number, elapsed: number, dark: boolean) {
  const colors = dark ? palettes.dark : palettes.light;
  const breath = (1 - Math.cos(elapsed / 3780 * tau)) / 2;
  const radius = .450 + .430 * breath;
  const keyAngle = -2.53 + .12 * Math.sin(elapsed / 8400 * tau);
  const keyX = .96 * Math.cos(keyAngle);
  const keyY = .96 * Math.sin(keyAngle);
  const yaw = .37 + elapsed / 6380 * tau;
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const project = ([x, y, z]: Point) => {
    const horizontal = x * cosYaw + z * sinYaw;
    const side = z * cosYaw - x * sinYaw;
    const depth = side * cosPitch + y * sinPitch;
    const vertical = y * cosPitch - side * sinPitch;
    const perspective = camera / (camera - depth * radius);
    return {
      x: horizontal * radius * perspective,
      y: vertical * radius * perspective,
      horizontal, vertical, depth, perspective
    };
  };
  const frontness = (depth: number) => clamp((depth + .52) / 1.36);

  const points = mesh.points.map(point => {
    const projected = project(point);
    const incidence = keyX * projected.horizontal + keyY * projected.vertical + .28 * projected.depth;
    const dusk = clamp((incidence + .105) / .32);
    const diffuse = .38 * dusk * dusk * (3 - 2 * dusk) + .62 * Math.max(0, incidence) ** .72;
    return { ...projected, daylight: clamp(diffuse) };
  });
  ctx.setTransform(half, 0, 0, half, half, half);
  ctx.clearRect(-1, -1, 2, 2);
  ctx.lineCap = 'round';

  ctx.strokeStyle = colors.edge;
  ctx.lineWidth = .025;
  for (const [i, j] of mesh.edges) {
    const a = points[i], b = points[j];
    const depth = frontness((a.depth + b.depth) / 2);
    const daylight = (a.daylight + b.daylight) / 2;
    const lit = .17 + .83 * daylight;
    ctx.globalAlpha = .012 + depth * .27 * lit * (.78 + .22 * breath);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  ctx.strokeStyle = colors.route;
  ctx.lineWidth = .028;
  ctx.globalAlpha = .13 * (.56 + .44 * breath);
  ctx.beginPath();
  lanes[2].path.map(project).forEach(({ x, y }, index) => {
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  for (const point of [...points].sort((a, b) => a.depth - b.depth)) {
    const depth = frontness(point.depth);
    const size = .048 * (.76 + .27 * depth) * (.88 + .12 * breath);
    const shadow = .41;
    const lit = shadow + (1 - shadow) * point.daylight;
    ctx.globalAlpha = (.29 + .71 * depth) * lit * (.86 + .14 * breath);
    ctx.fillStyle = rgbMix(colors.shade, colors.sun, point.daylight);
    ctx.beginPath();
    ctx.arc(point.x, point.y, size * point.perspective, 0, tau);
    ctx.fill();
  }

  lanes.forEach((lane, i) => {
    const phase = (elapsed / (1730 + i * 340) + i * .39) % 1;
    const travel = phase / .86;
    const launch = .16;
    const distance = travel < launch ? travel * travel / (2 * launch) : travel - launch / 2;
    const head = distance / (1 - launch / 2);
    const tail = .21;
    const brightness = clamp((1 - phase) / .135) * clamp(phase / .055);
    ctx.strokeStyle = i === 2 ? colors.core : colors.pulse;
    ctx.lineWidth = .061;
    for (let step = 0; step < 12; step++) {
      const from = head - tail + tail * step / 12;
      const to = from + tail / 12;
      if (to <= 0 || from >= 1) continue;
      const a = project(position(lane, from)), b = project(position(lane, to));
      ctx.globalAlpha = brightness * (.15 + .85 * step / 11) * (.58 + .42 * frontness(b.depth));
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    const tip = project(position(lane, head));
    ctx.globalAlpha = brightness * (.66 + .34 * frontness(tip.depth)) * clamp((1.035 - head) / .070);
    ctx.fillStyle = colors.tip;
    ctx.beginPath();
    ctx.arc(tip.x, tip.y, .062 * tip.perspective, 0, tau);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

export function ThinkingSphere() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    const root = document.documentElement;
    const pixels = Math.round(24 * Math.min(window.devicePixelRatio || 1, 2));
    canvas.width = canvas.height = pixels;
    const half = pixels / 2;
    let elapsed = 1520;
    let previous: number | undefined;
    let frame = 0;
    let dark = false;

    const tick = (time: number) => {
      previous ??= time;
      if (time - previous >= 30) {
        elapsed += Math.min(time - previous, 64);
        previous = time;
        drawSphere(ctx, half, elapsed, dark);
      }
      frame = requestAnimationFrame(tick);
    };
    const syncAppearance = () => {
      cancelAnimationFrame(frame);
      previous = undefined;
      dark = root.classList.contains('dark');
      drawSphere(ctx, half, elapsed, dark);
      if (root.dataset.reduceMotion !== 'true') frame = requestAnimationFrame(tick);
    };
    const observer = new MutationObserver(syncAppearance);
    observer.observe(root, { attributes: true, attributeFilter: ['class', 'data-reduce-motion'] });
    syncAppearance();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, []);

  return <canvas ref={ref} className="um-agent-thinking-icon" aria-hidden="true" />;
}
