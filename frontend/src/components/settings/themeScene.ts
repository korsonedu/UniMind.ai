// Material colour and emitted light are composed at the scene's native 176 × 50 resolution.
const W = 176, H = 50;
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
const clamp = (n: number, min = 0, max = 1) => Math.max(min, Math.min(max, n));
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
type Activity = 'music' | 'read' | 'water' | 'stretch' | 'sleep' | 'stars';
const DAY_ACTIVITIES: Activity[] = ['music', 'read', 'water', 'stretch'];
const NIGHT_ACTIVITIES: Activity[] = ['sleep', 'read', 'stars'];
const ACTIVITY_SPOTS: Record<Activity, [number, number]> = {
  music: [101, 27], read: [94, 28], water: [131, 28], stretch: [101, 27], sleep: [70, 29], stars: [123, 28],
};

export function createThemeScene(canvas: HTMLCanvasElement, reduced: boolean) {
  const context = canvas.getContext('2d')!;
  const layers = Array.from({ length: 3 }, () => {
    const layer = document.createElement('canvas'); layer.width = W; layer.height = H; return layer;
  });
  const albedo = layers[0].getContext('2d', { willReadFrequently: true })!;
  const emission = layers[1].getContext('2d', { willReadFrequently: true })!;
  const composite = layers[2].getContext('2d')!;
  const frame = composite.createImageData(W, H), source = new Uint8ClampedArray(W * H * 4);
  const scale = Math.min(window.devicePixelRatio || 1, 3);
  canvas.width = W * scale; canvas.height = H * scale;
  context.scale(scale, scale); context.imageSmoothingEnabled = false;
  let target = 1, targetDay = 1, position = 1, day = 1, velocity = 0;
  let raf = 0, previous = 0, elapsed = 0, visible = true, disposed = false;
  const rect = (ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, colour: string) => {
    if (ctx === albedo) {
      emission.save(); emission.setTransform(albedo.getTransform());
      emission.clearRect(Math.round(x), Math.round(y), w, h); emission.restore();
    }
    ctx.fillStyle = colour; ctx.fillRect(Math.round(x), Math.round(y), w, h);
  };

  function mascot(x: number, y: number, awake: number, time: number, activity: Activity) {
    albedo.save(); albedo.translate(Math.round(x), Math.round(y + (awake > .65 ? Math.sin(time * (activity === 'music' ? 5 : 2)) * .7 : 0)));
    // The logo's double arch, two eyes and floating upper-right dot.
    albedo.rotate(-Math.PI / 2 * (1 - clamp(awake * 3)));
    const body = new Path2D(); body.moveTo(-7, 2); body.lineTo(-7, -4);
    body.bezierCurveTo(-7, -9, -2, -9, 0, -5); body.bezierCurveTo(3, -9, 8, -9, 8, -4);
    body.lineTo(8, 2); body.bezierCurveTo(8, 11, -7, 11, -7, 2);
    // Foreground objects occlude the skyline's emitted window light.
    emission.save(); emission.setTransform(albedo.getTransform());
    emission.globalCompositeOperation = 'destination-out'; emission.fill(body); emission.restore();
    albedo.fillStyle = '#8474ef'; albedo.fill(body);
    albedo.fillStyle = '#efecff'; albedo.beginPath(); albedo.roundRect(-5, -4, 11, 10, 4); albedo.fill();
    rect(albedo, -2, -2, 1, awake > .3 ? 3 : 1, '#383064'); rect(albedo, 3, -2, 1, awake > .3 ? 3 : 1, '#383064');
    rect(albedo, 9, -9, 2, 2, '#aa8bff');
    rect(albedo, -3, 8, 2, 3, '#54469c'); rect(albedo, 4, 8, 2, 3, '#54469c');
    if (awake > .65 && activity === 'music') {
      albedo.strokeStyle = '#282740'; albedo.lineWidth = 2;
      albedo.beginPath(); albedo.arc(.5, -2, 8, Math.PI, 2 * Math.PI); albedo.stroke();
      rect(albedo, -8, -3, 3, 5, '#30334b'); rect(albedo, 6, -3, 3, 5, '#30334b'); rect(albedo, 7, 5, 5, 2, '#a797f5');
      emission.fillStyle = '#c5afff'; emission.font = '8px sans-serif';
      for (let i = 0; i < 2; i++) {
        const phase = (time * .42 + i * .5) % 1;
        emission.globalAlpha = Math.sin(phase * Math.PI);
        emission.fillText(i ? '♪' : '♫', x + 10 + i * 7, y - 5 - phase * 13);
      }
      emission.globalAlpha = 1;
    } else if (awake > .65 && activity === 'read') {
      // An open book, with a gently turning page.
      rect(albedo, -9, 2, 8, 6, '#e9c991'); rect(albedo, -1, 2, 8, 6, '#faf0d1');
      rect(albedo, -1, 2, 1, 7, '#93746d');
      rect(albedo, -7, 4, 4, 1, '#b49b85'); rect(albedo, 1, 4, 4, 1, '#b49b85');
      rect(albedo, Math.sin(time * 1.5) * 3, 1, 1, 7, '#fff5da');
    } else if (awake > .65 && activity === 'water') {
      rect(albedo, 7, 3, 7, 2, '#b0a0f2'); rect(albedo, 11, 2, 6, 5, '#7cc6c3');
      rect(albedo, 16, 2, 4, 2, '#9ae2d6');
      for (let i = 0; i < 3; i++) rect(emission, x + 18 + i, y + 5 + (time * 7 + i * 2) % 6, 1, 1, '#9bdded');
    } else if (awake > .65 && activity === 'stretch') {
      const lift = Math.round(Math.sin(time * 2) * 2);
      rect(albedo, -11, -5 + lift, 5, 2, '#a797f5'); rect(albedo, -12, -9 + lift, 2, 6, '#a797f5');
      rect(albedo, 7, -5 + lift, 5, 2, '#a797f5'); rect(albedo, 11, -9 + lift, 2, 6, '#a797f5');
    } else if (awake > .65 && activity === 'stars') {
      rect(albedo, 7, 2, 6, 2, '#a797f5');
    } else if (awake < .25) {
      emission.fillStyle = '#a5b7ec'; emission.font = '6px monospace';
      emission.fillText('z', x + 9, y - 8 - Math.sin(time) * 2);
    }
    albedo.restore();
  }

  function draw(time: number) {
    albedo.clearRect(0, 0, W, H); emission.clearRect(0, 0, W, H);
    const terminator = mix(197, -21, day);
    const localDay = (x: number) => clamp((x - terminator + 20) / 40);
    // The skyline's small events have independent periods, so their combinations change.
    const birdFlight = time % 17;
    if (birdFlight < 8) for (let i = 0; i < 3; i++) {
      const x = -18 + birdFlight * 28 - i * 9, y = 8 + i * 3;
      albedo.globalAlpha = localDay(x);
      rect(albedo, x, y, 1, 1, '#43566e');
      rect(albedo, x - 2, y - Math.round(Math.sin(time * 8 + i)), 2, 1, '#43566e');
      rect(albedo, x + 1, y - Math.round(Math.sin(time * 8 + i)), 2, 1, '#43566e');
    }
    albedo.globalAlpha = 1;
    for (let i = 0; i < 15; i++) {
      const x = i * 14 - 5, height = 9 + (i * 17 % 22), y = 40 - height;
      rect(albedo, x, y, 10, height, i % 2 ? '#718098' : '#596a84'); rect(albedo, x + 2, y - 2, 6, 2, '#8c99ae');
      if (i % 3 === 0) rect(albedo, x + 5, y - 6, 1, 4, '#70809a');
      for (let row = y + 4; row < 39; row += 5) for (let col = x + 2; col < x + 9; col += 4) {
        rect(albedo, col, row, 2, 2, '#b1c7d3');
        if ((row + col) % 3) {
          emission.globalAlpha = (1 - clamp((col - terminator + 16) / 32)) * .85;
          rect(emission, col, row, 2, 2, '#ffce82');
        }
      }
    }
    emission.globalAlpha = 1;
    rect(albedo, 18, 30, 25, 13, '#8693a2'); rect(albedo, 22, 27, 17, 3, '#a7b0bb'); rect(albedo, 27, 23, 7, 4, '#6c7b8e');
    rect(albedo, 133, 31, 24, 12, '#6e7d90'); rect(albedo, 137, 27, 15, 4, '#8591a0');
    const trainPass = time % 23;
    if (trainPass < 9) {
      const x = -44 + trainPass * 29;
      rect(albedo, x, 35, 39, 4, '#b7becb');
      emission.clearRect(Math.round(x), 35, 39, 4);
      for (let car = 0; car < 3; car++) {
        rect(albedo, x + car * 13 + 1, 36, 9, 2, '#718caa');
        emission.globalAlpha = (1 - localDay(x + car * 13)) * .7;
        rect(emission, x + car * 13 + 1, 36, 9, 1, '#ffe1a5');
      }
      emission.globalAlpha = 1;
    }
    rect(albedo, 0, 39, W, 1, '#667489');
    rect(albedo, 0, 42, W, 8, '#a87875');
    for (let y = 44; y < 50; y += 4) {
      rect(albedo, 0, y, W, 1, '#675363');
      for (let x = (y % 8) * 2; x < W; x += 12) rect(albedo, x, y - 3, 1, 3, '#675363');
    }
    rect(albedo, 0, 40, W, 2, '#d5bcc0'); rect(albedo, 0, 42, W, 1, '#554b65');
    // Bed, blanket, workstation and chair.
    rect(albedo, 59, 34, 24, 5, '#827baf'); rect(albedo, 58, 31, 2, 9, '#cfac94'); rect(albedo, 81, 35, 2, 5, '#cfac94');
    rect(albedo, 61, 32, 7, 3, '#e2d9ef'); rect(albedo, 68, 33, 13, 5, '#8a8fd1');
    rect(albedo, 108, 32, 20, 2, '#d8ad91'); rect(albedo, 110, 34, 2, 6, '#977b7f'); rect(albedo, 124, 34, 2, 6, '#977b7f');
    rect(albedo, 113, 23, 12, 8, '#30394e'); rect(albedo, 118, 31, 2, 1, '#45415b');
    emission.globalAlpha = .45 + day * .55;
    rect(emission, 114, 24, 10, 6, '#89d5e6'); rect(emission, 115, 25, 5, 1, '#e0f6f4'); emission.globalAlpha = 1;
    // A plant and a cat give the roof a life beyond the workstation.
    rect(albedo, 145, 35, 5, 5, '#c08d79'); rect(albedo, 144, 34, 7, 2, '#ddb29a');
    rect(albedo, 147, 27, 1, 7, '#77a68b');
    rect(albedo, 143, 28, 4, 2, '#8abf91'); rect(albedo, 148, 30, 4, 2, '#a0c99b');
    const catWalk = time % 29, catX = 39 + Math.min(catWalk, 5, 29 - catWalk) * 2;
    const step = catWalk < 5 || catWalk > 24 ? Math.round(Math.sin(time * 9)) : 0;
    rect(albedo, catX, 34, 8, 5, '#d4a67e'); rect(albedo, catX + 5, 31, 5, 5, '#e5bc94');
    rect(albedo, catX + 5, 30, 1, 2, '#e5bc94'); rect(albedo, catX + 9, 30, 1, 2, '#e5bc94');
    rect(albedo, catX + 1, 38, 2, 2 + step, '#bc8a6e'); rect(albedo, catX + 6, 38, 2, 2 - step, '#bc8a6e');
    rect(albedo, catX - 3, 33 + Math.round(Math.sin(time * 2)), 4, 2, '#d4a67e');
    const activities = day > .3 ? DAY_ACTIVITIES : NIGHT_ACTIVITIES;
    const index = Math.floor(time / 12) % activities.length, activity = activities[index];
    const previousActivity = time < 12 ? activity : activities[(index + activities.length - 1) % activities.length];
    const from = ACTIVITY_SPOTS[previousActivity], to = ACTIVITY_SPOTS[activity];
    const travelSeconds = Math.max(.12, Math.hypot(to[0] - from[0], to[1] - from[1]) / 75);
    const phase = clamp((time % 12) / (travelSeconds * 2)), transition = phase * phase * (3 - 2 * phase);
    const wake = mix(previousActivity === 'sleep' ? 0 : 1, activity === 'sleep' ? 0 : 1, transition);
    if (activity === 'stars') {
      // Telescope: angled tube and a tripod, visible before the mascot approaches.
      albedo.strokeStyle = '#b3bbd5'; albedo.lineWidth = 2;
      albedo.beginPath(); albedo.moveTo(135, 30); albedo.lineTo(143, 23); albedo.stroke();
      rect(albedo, 141, 22, 4, 3, '#d6d9e8');
      albedo.lineWidth = 1; albedo.beginPath(); albedo.moveTo(139, 28); albedo.lineTo(134, 40);
      albedo.moveTo(139, 28); albedo.lineTo(143, 40); albedo.stroke();
    }
    mascot(mix(from[0], to[0], transition), mix(from[1], to[1], transition), wake, time / 2, activity);
    if (wake < .35) rect(albedo, 68, 33, 13, 5, '#8a8fd1');
    if (activity === 'music' || activity === 'read') { rect(albedo, 96, 35, 10, 2, '#50536f'); rect(albedo, 99, 37, 2, 3, '#50536f'); }
    const a = albedo.getImageData(0, 0, W, H).data, e = emission.getImageData(0, 0, W, H).data;
    const cloudX = (time * 1.8 + 37) % 220 - 20, meteor = time % 31;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const p = (y * W + x) * 4, horizon = y / H;
      const dawn = Math.exp(-Math.pow((x - terminator) / 22, 2)), daylight = clamp((x - terminator + 20) / 40);
      const dither = BAYER[(y % 4) * 4 + x % 4] / 16 - .5;
      const night = [14 + horizon * 22, 20 + horizon * 23, 48 + horizon * 27];
      const morning = [100 + horizon * 92, 178 + horizon * 30, 222 + horizon * 5];
      const sky = night.map((n, c) => mix(n, morning[c], daylight) + dawn * [95, 35, 12][c] * horizon);
      const cloud = Math.pow((x - cloudX) / 12, 2) + Math.pow((y - 7) / 2, 2) < 1
        || Math.pow((x - cloudX - 8) / 8, 2) + Math.pow((y - 8) / 2, 2) < 1;
      if (cloud) for (let c = 0; c < 3; c++) sky[c] = mix(sky[c], [221, 237, 244][c], daylight * .65);
      if (meteor > 7 && meteor < 8.6) {
        const headX = 35 + (meteor - 7) * 58, tail = headX - x;
        if (tail >= 0 && tail < 12 && Math.abs(y - (3 + (x - 35) * .12)) < .65) {
          for (let c = 0; c < 3; c++) sky[c] += (1 - daylight) * (1 - tail / 12) * [145, 173, 200][c];
        }
      }
      if (y < 25 && (x * 7919 + y * 1049) % 173 === 0) {
        for (let c = 0; c < 3; c++) sky[c] += (1 - daylight) * 125 * (.7 + .3 * Math.sin(time * 1.4 + x));
      }
      if (Math.hypot(x - 145, y - 12) < 4) for (let c = 0; c < 3; c++) sky[c] = mix(sky[c], [248, 188, 131][c], 1 - daylight);
      const sunX = clamp(terminator + 30, 20, 163), sunY = 23 - Math.sin(day * Math.PI / 2) * 16;
      if (Math.hypot(x - sunX, y - sunY) < 4) for (let c = 0; c < 3; c++) sky[c] = mix(sky[c], [255, 238, 180][c], daylight);
      const solid = a[p + 3] > 100;
      const top = solid && (y === 0 || a[p - W * 4 + 3] < 100), bottom = solid && (y === H - 1 || a[p + W * 4 + 3] < 100);
      const outline = !solid && ((x > 0 && a[p - 1] > 100) || (x < W - 1 && a[p + 7] > 100) || (y < H - 1 && a[p + W * 4 + 3] > 100));
      const brightness = Math.floor((.42 + daylight * .49 + dawn * .15 + (top ? .24 : 0) + (bottom ? .08 : 0)) * 5 + dither) / 5;
      for (let c = 0; c < 3; c++) {
        const base = solid ? a[p + c] * brightness + (top ? [18, 13, 22][c] : 0) : outline ? sky[c] * .55 : sky[c];
        frame.data[p + c] = clamp(base + e[p + c] * e[p + 3] / 255, 0, 255);
      }
      frame.data[p + 3] = 255;
    }
    // Refract the finished scene. RGB samples separate toward the glass rim.
    source.set(frame.data);
    const cx = 24 + position * 64, stretch = reduced ? 0 : clamp(velocity * .065, -.16, .16);
    const rx = 17 + Math.abs(stretch) * 24, ry = 22 - Math.abs(stretch) * 12;
    // Grow only the side approaching the capsule end, including its full height.
    const leftAttach = clamp(1 - position), rightAttach = clamp(position - 1);
    const attachment = Math.max(leftAttach, rightAttach);
    const left = mix(cx - rx, 0, leftAttach), right = mix(cx + rx, W, rightAttach);
    const halfHeight = mix(ry, H / 2, attachment);
    const corner = Math.min(rx, ry);
    const leftCorner = mix(corner, Math.min(H / 2, right - left - corner), leftAttach);
    const rightCorner = mix(corner, Math.min(H / 2, right - left - corner), rightAttach);
    for (let y = 0; y < H; y++) for (let x = Math.max(0, Math.floor(left)); x < Math.min(W, right); x++) {
      const sideWidth = x < cx ? cx - left : right - cx, sideCorner = x < cx ? leftCorner : rightCorner;
      const nx = (x - cx) / sideWidth, ny = (y - 25) / halfHeight;
      const edgeX = Math.max(Math.abs(x - cx) - (sideWidth - sideCorner), 0) / sideCorner;
      const edgeY = Math.max(Math.abs(y - 25) - (halfHeight - sideCorner), 0) / sideCorner;
      const radius = edgeX * edgeX + edgeY * edgeY;
      if (radius >= 1) continue;
      const bend = .77 + radius * .16, sx = cx + (x - cx) * bend + stretch * ny * 5, sy = 25 + (y - 25) * bend;
      for (let c = 0; c < 3; c++) {
        const chroma = (c - 1) * radius * 1.6;
        const sample = (Math.round(clamp(sy, 0, H - 1)) * W + Math.round(clamp(sx + nx * chroma, 0, W - 1))) * 4;
        frame.data[(y * W + x) * 4 + c] = source[sample + c] * .94 + 11 + radius * radius * [9, 13, 22][c];
      }
    }
    composite.putImageData(frame, 0, 0); context.clearRect(0, 0, W, H); context.drawImage(layers[2], 0, 0);
    context.save(); context.translate(cx, 25); context.rotate(stretch * .45 * (1 - attachment));
    context.beginPath(); context.roundRect(left - cx, -halfHeight, right - left, halfHeight * 2, [leftCorner, rightCorner, rightCorner, leftCorner]);
    const glass = context.createLinearGradient(left - cx, -halfHeight, right - cx, halfHeight);
    glass.addColorStop(0, '#ffffffa8'); glass.addColorStop(.24, '#ffffff0a'); glass.addColorStop(.72, '#c3d4ff08'); glass.addColorStop(1, '#b0d2ff75');
    context.fillStyle = glass; context.fill(); context.strokeStyle = '#ffffff90'; context.lineWidth = .8; context.stroke();
    context.beginPath(); context.moveTo(left - cx + 2, 1); context.lineTo(left - cx + 2, -halfHeight + leftCorner);
    context.arc(left - cx + leftCorner, -halfHeight + leftCorner, leftCorner - 2, Math.PI, Math.PI * 1.68);
    context.strokeStyle = '#ffffffd0'; context.lineWidth = 1.4; context.stroke();
    context.beginPath(); context.moveTo(right - cx - 2, -1); context.lineTo(right - cx - 2, halfHeight - rightCorner);
    context.arc(right - cx - rightCorner, halfHeight - rightCorner, rightCorner - 2, 0, 1.1);
    context.strokeStyle = '#a1baffb0'; context.lineWidth = .8; context.stroke(); context.restore();
  }

  function tick(now: number) {
    raf = 0;
    if (!visible || document.hidden || disposed) { previous = 0; return; }
    const dt = previous ? Math.min((now - previous) / 1000, .032) : 1 / 60;
    previous = now; elapsed += dt * 2;
    velocity += ((target - position) * 210 - velocity * 19) * dt; position += velocity * dt;
    day += (targetDay - day) * Math.min(1, dt * 7); draw(elapsed);
    if (!reduced) raf = requestAnimationFrame(tick);
  }
  function resume() {
    if (!visible || document.hidden || disposed) return;
    if (reduced) draw(0); else if (!raf) raf = requestAnimationFrame(tick);
  }
  const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; resume(); });
  observer.observe(canvas); document.addEventListener('visibilitychange', resume);
  return {
    update(next: number, daylight: number) {
      target = next; targetDay = daylight;
      if (reduced) { position = target; day = targetDay; velocity = 0; draw(0); } else resume();
    },
    destroy() { disposed = true; cancelAnimationFrame(raf); observer.disconnect(); document.removeEventListener('visibilitychange', resume); },
  };
}
