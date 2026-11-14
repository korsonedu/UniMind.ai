// Material colour and emitted light are composed at the scene's native 176 × 50 resolution.
const W = 176, H = 50;
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
const clamp = (n: number, min = 0, max = 1) => Math.max(min, Math.min(max, n));
const mix = (a: number, b: number, t: number) => a + (b - a) * t;

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
    ctx.fillStyle = colour; ctx.fillRect(Math.round(x), Math.round(y), w, h);
  };

  function mascot(x: number, y: number, awake: number, time: number) {
    albedo.save(); albedo.translate(Math.round(x), Math.round(y + (awake > .65 ? Math.sin(time * 5) * .7 : 0)));
    // The logo's double arch, two eyes and floating upper-right dot.
    albedo.rotate(-Math.PI / 2 * (1 - clamp(awake * 3)));
    albedo.fillStyle = '#8474ef'; albedo.beginPath();
    albedo.moveTo(-7, 2); albedo.lineTo(-7, -4);
    albedo.bezierCurveTo(-7, -9, -2, -9, 0, -5); albedo.bezierCurveTo(3, -9, 8, -9, 8, -4);
    albedo.lineTo(8, 2); albedo.bezierCurveTo(8, 11, -7, 11, -7, 2); albedo.fill();
    albedo.fillStyle = '#efecff'; albedo.beginPath(); albedo.roundRect(-5, -4, 11, 10, 4); albedo.fill();
    rect(albedo, -2, -2, 1, awake > .3 ? 3 : 1, '#383064'); rect(albedo, 3, -2, 1, awake > .3 ? 3 : 1, '#383064');
    rect(albedo, 9, -9, 2, 2, '#aa8bff');
    rect(albedo, -3, 8, 2, 3, '#54469c'); rect(albedo, 4, 8, 2, 3, '#54469c');
    if (awake > .65) {
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
    } else if (awake < .25) {
      emission.fillStyle = '#a5b7ec'; emission.font = '6px monospace';
      emission.fillText('z', x + 9, y - 8 - Math.sin(time) * 2);
    }
    albedo.restore();
  }

  function draw(time: number) {
    albedo.clearRect(0, 0, W, H); emission.clearRect(0, 0, W, H);
    const terminator = mix(197, -21, day);
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
    const wake = clamp((day - .18) / .64);
    mascot(mix(70, 101, wake), mix(29, 27, Math.sin(wake * Math.PI / 2)), wake, time);
    if (wake < .35) rect(albedo, 68, 33, 13, 5, '#8a8fd1');
    if (wake > .65) { rect(albedo, 96, 35, 10, 2, '#50536f'); rect(albedo, 99, 37, 2, 3, '#50536f'); }
    const a = albedo.getImageData(0, 0, W, H).data, e = emission.getImageData(0, 0, W, H).data;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const p = (y * W + x) * 4, horizon = y / H;
      const dawn = Math.exp(-Math.pow((x - terminator) / 22, 2)), daylight = clamp((x - terminator + 20) / 40);
      const dither = BAYER[(y % 4) * 4 + x % 4] / 16 - .5;
      const night = [14 + horizon * 22, 20 + horizon * 23, 48 + horizon * 27];
      const morning = [100 + horizon * 92, 178 + horizon * 30, 222 + horizon * 5];
      const sky = night.map((n, c) => mix(n, morning[c], daylight) + dawn * [95, 35, 12][c] * horizon);
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
    const corner = Math.min(rx, ry);
    for (let y = 1; y < H - 1; y++) for (let x = Math.max(0, Math.floor(cx - rx)); x < Math.min(W, cx + rx); x++) {
      const nx = (x - cx) / rx, ny = (y - 25) / ry;
      const edgeX = Math.max(Math.abs(x - cx) - (rx - corner), 0) / corner;
      const edgeY = Math.max(Math.abs(y - 25) - (ry - corner), 0) / corner;
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
    context.save(); context.translate(cx, 25); context.rotate(stretch * .45);
    context.beginPath(); context.roundRect(-rx, -ry, rx * 2, ry * 2, corner);
    const glass = context.createLinearGradient(-rx, -ry, rx, ry);
    glass.addColorStop(0, '#ffffffa8'); glass.addColorStop(.24, '#ffffff0a'); glass.addColorStop(.72, '#c3d4ff08'); glass.addColorStop(1, '#b0d2ff75');
    context.fillStyle = glass; context.fill(); context.strokeStyle = '#ffffff90'; context.lineWidth = .8; context.stroke();
    context.beginPath(); context.moveTo(-rx + 2, 1); context.lineTo(-rx + 2, -ry + corner);
    context.arc(-rx + corner, -ry + corner, corner - 2, Math.PI, Math.PI * 1.68);
    context.strokeStyle = '#ffffffd0'; context.lineWidth = 1.4; context.stroke();
    context.beginPath(); context.moveTo(rx - 2, -1); context.lineTo(rx - 2, ry - corner);
    context.arc(rx - corner, ry - corner, corner - 2, 0, 1.1);
    context.strokeStyle = '#a1baffb0'; context.lineWidth = .8; context.stroke(); context.restore();
  }

  function tick(now: number) {
    raf = 0;
    if (!visible || document.hidden || disposed) { previous = 0; return; }
    const dt = previous ? Math.min((now - previous) / 1000, .032) : 1 / 60;
    previous = now; elapsed += dt;
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
