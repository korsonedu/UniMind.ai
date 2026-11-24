// WBI's public permutation and RFC 1321 MD5, implemented locally for MAIN world.
export const MIXIN_KEY_ENC_TAB = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
  27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
  37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
  22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
] as const;

export function getWbiMixinKey(imgUrl: string, subUrl: string): string {
  const imageKey = imgUrl.split(/[?#]/)[0]!.split('/').pop()?.replace(/\.[^.]+$/, '') ?? '';
  const subKey = subUrl.split(/[?#]/)[0]!.split('/').pop()?.replace(/\.[^.]+$/, '') ?? '';
  const combined = imageKey + subKey;
  if (combined.length < 64) throw new Error('Incomplete WBI image keys');
  return MIXIN_KEY_ENC_TAB.slice(0, 32).map(index => combined[index]).join('');
}

export function md5Hex(input: string): string {
  const inputBytes = new TextEncoder().encode(input);
  const blockCount = Math.ceil((inputBytes.length + 9) / 64);
  const bytes = new Uint8Array(blockCount * 64);
  bytes.set(inputBytes);
  bytes[inputBytes.length] = 128;
  const words = new DataView(bytes.buffer);
  words.setUint32(bytes.length - 8, inputBytes.length * 8, true);
  words.setUint32(bytes.length - 4, Math.floor(inputBytes.length / 0x20000000), true);
  const state: [number, number, number, number] = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476];
  const rotations = [[7, 12, 17, 22], [5, 9, 14, 20], [4, 11, 16, 23], [6, 10, 15, 21]];
  for (let block = 0; block < bytes.length; block += 64) {
    let [a, b, c, d] = state;
    for (let step = 0; step < 64; step += 1) {
      const round = Math.floor(step / 16);
      let expression: number;
      let wordIndex: number;
      switch (round) {
        case 0: expression = (b & c) | (~b & d); wordIndex = step; break;
        case 1: expression = (d & b) | (~d & c); wordIndex = (5 * step + 1) % 16; break;
        case 2: expression = b ^ c ^ d; wordIndex = (3 * step + 5) % 16; break;
        default: expression = c ^ (b | ~d); wordIndex = (7 * step) % 16;
      }
      const constant = Math.floor(Math.abs(Math.sin(step + 1)) * 0x100000000);
      const sum = (a + expression + constant + words.getUint32(block + wordIndex * 4, true)) | 0;
      const rotation = rotations[round]![step % 4]!;
      const nextB = (b + ((sum << rotation) | (sum >>> (32 - rotation)))) | 0;
      a = d;
      d = c;
      c = b;
      b = nextB;
    }
    state[0] = (state[0] + a) | 0;
    state[1] = (state[1] + b) | 0;
    state[2] = (state[2] + c) | 0;
    state[3] = (state[3] + d) | 0;
  }
  const digest = new DataView(new ArrayBuffer(16));
  state.forEach((value, index) => digest.setUint32(index * 4, value, true));
  return Array.from(new Uint8Array(digest.buffer), byte => byte.toString(16).padStart(2, '0')).join('');
}

export function signWbiParams(
  params: Record<string, string | number>, imgUrl: string, subUrl: string,
  timestamp = Math.floor(Date.now() / 1000),
): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries({ ...params, wts: timestamp })) {
    if (key !== 'w_rid') result[key] = String(value).replace(/[!'()*]/g, '');
  }
  const query = Object.keys(result).sort()
    .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(result[key]!)}`).join('&');
  result.w_rid = md5Hex(query + getWbiMixinKey(imgUrl, subUrl));
  return result;
}
