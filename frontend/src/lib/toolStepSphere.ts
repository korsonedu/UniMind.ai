type Point = [number, number, number];
export type ToolStepMode = 'call' | 'analysis';
export const TOOL_STEP_ANIMATION_MS = 3600;
const seedCount = 3;
const surface: { cube: Point; sphere: Point }[] = [];
const edges: [number, number][] = [];
const grid = [-1, -1 / 3, 1 / 3, 1];

for (const x of grid) {
  for (const y of grid) {
    for (const z of grid) {
      if (Math.max(Math.abs(x), Math.abs(y), Math.abs(z)) !== 1) continue;
      const radius = Math.hypot(x, y, z);
      surface.push({ cube: [x, y, z], sphere: [x / radius, y / radius, z / radius] });
    }
  }
}
for (const [i, { cube: [x, y, z] }] of surface.entries()) {
  for (let j = i + 1; j < surface.length; j++) {
    const [a, b, c] = surface[j].cube;
    if (Math.hypot(x - a, y - b, z - c) < .7) edges.push([i, j]);
  }
}

const callOrder = surface.map((_, index) => (index * 19 + 9) % surface.length);
const clamp = (value: number) => Math.min(1, Math.max(0, value));
const ease = (value: number) => {
  const x = clamp(value);
  return x * x * (3 - 2 * x);
};

export function drawToolStepSphere(ctx: CanvasRenderingContext2D, half: number, mode: ToolStepMode, progress: number, dark: boolean) {
  const morph = mode === 'analysis' ? ease((progress - .13) / .25) * (1 - ease((progress - .61) / .29)) : 0;
  const yaw = -.55 + .48 * ease(progress);
  const cosYaw = Math.cos(yaw), sinYaw = Math.sin(yaw);
  const cosPitch = Math.cos(.37), sinPitch = Math.sin(.37);
  const size = .76 - .16 * morph;
  const ink = dark ? '#aebefc' : '#556eb8';
  const accent = dark ? '#ffb76e' : '#c97134';
  const points = surface.map(({ cube, sphere }, index) => {
    const x = sphere[0] + (cube[0] - sphere[0]) * morph;
    const y = sphere[1] + (cube[1] - sphere[1]) * morph;
    const z = sphere[2] + (cube[2] - sphere[2]) * morph;
    const lateral = x * cosYaw + z * sinYaw;
    const side = z * cosYaw - x * sinYaw;
    const depth = side * cosPitch + y * sinPitch;
    const scale = size * 4.6 / (4.6 - depth * size);
    const rank = callOrder[index];
    const start = .08 + (rank - seedCount) / (surface.length - seedCount - 1) * .78;
    const arrival = mode === 'analysis' || rank < seedCount ? 1 : ease((progress - start) / .12);
    return { x: lateral * scale, y: (y * cosPitch - side * sinPitch) * scale, depth, arrival, index };
  });

  ctx.setTransform(half, 0, 0, half, half, half);
  ctx.clearRect(-1, -1, 2, 2);
  ctx.lineCap = 'round';
  ctx.lineWidth = .013 + .012 * morph;
  ctx.strokeStyle = ink;
  ctx.globalAlpha = .12 + .25 * morph;
  for (const [i, j] of edges) {
    const a = points[i], b = points[j];
    if (a.arrival < 1 || b.arrival < 1) continue;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  for (const { x, y, depth, arrival, index } of points.sort((a, b) => a.depth - b.depth)) {
    if (arrival === 0) continue;
    if (arrival === 1) {
      const front = clamp((depth + 1) / 2);
      ctx.fillStyle = ink;
      ctx.globalAlpha = .26 + .73 * front;
      ctx.beginPath();
      ctx.arc(x, y, .032 + .019 * front, 0, 2 * Math.PI);
      ctx.fill();
    } else {
      const angle = Math.atan2(y, x) + (index % 3 - 1) * .28;
      const dx = Math.cos(angle), dy = Math.sin(angle);
      const remaining = (1 - arrival) * .47;
      const fromX = x + dx * remaining;
      const fromY = y + dy * remaining;
      const glow = clamp(12 * arrival);
      const trail = .14 * Math.sin(arrival * Math.PI);

      ctx.strokeStyle = accent;
      ctx.globalAlpha = .38 * glow;
      ctx.beginPath();
      ctx.moveTo(fromX, fromY);
      ctx.lineTo(fromX + dx * trail, fromY + dy * trail);
      ctx.stroke();
      ctx.fillStyle = accent;
      ctx.globalAlpha = glow;
      ctx.beginPath();
      ctx.arc(fromX, fromY, .06, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
}
