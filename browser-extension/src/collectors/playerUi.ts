import type { VideoPlatform } from '../shared/types';

type PlayerPlatform = Extract<VideoPlatform, 'bilibili' | 'youtube'>;

const PLAYERS = {
  bilibili: '#bilibili-player, #bilibiliPlayer, .bpx-player, .bpx-player-container',
  youtube: '#movie_player, ytd-reel-video-renderer[is-active]',
};

const TITLES = {
  bilibili: 'h1.video-title, .video-info h1, #viewbox_report h1, [class*="mediainfo_mediaTitle"]',
  youtube: 'ytd-watch-metadata h1, #above-the-fold #title h1, ytd-reel-video-renderer[is-active] h2',
};

const BUTTON_STYLES = `
  :host {
    all: initial !important;
    display: inline-flex !important;
    vertical-align: middle !important;
    align-self: center !important;
    flex: 0 0 auto !important;
    margin: 0 4px !important;
    --um-color-surface: #ffffff;
    --um-color-text: #202226;
    --um-color-border: #e2e5e9;
    --um-color-hover: #eef0f3;
    --um-color-accent: #4f5fa6;
  }
  button {
    all: unset;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    box-sizing: border-box;
    min-height: 28px;
    padding: 4px 10px;
    border: 1px solid var(--um-color-border);
    border-radius: 999px;
    background: var(--um-color-surface);
    color: var(--um-color-text);
    font: 500 12px/18px -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    white-space: nowrap;
    cursor: pointer;
    transition: background-color 150ms ease, border-color 150ms ease;
  }
  .brand-dot { width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: var(--um-color-accent); }
  button:hover { background: var(--um-color-hover); }
  button:active { border-color: var(--um-color-accent); }
  button:focus-visible { outline: 2px solid var(--um-color-accent); outline-offset: 2px; }
  @media (prefers-color-scheme: dark) {
    :host {
      --um-color-surface: #202227;
      --um-color-text: #eceef2;
      --um-color-border: #343840;
      --um-color-hover: #2a2e35;
      --um-color-accent: #a8b6f0;
    }
  }
  @media (prefers-reduced-motion: reduce) { button { transition: none; } }
`;

export function findPlayerVideo(platform: PlayerPlatform): HTMLVideoElement | null {
  const fullscreen = document.fullscreenElement;
  if (fullscreen instanceof HTMLVideoElement) return fullscreen;
  const fullscreenVideo = fullscreen?.querySelector('video');
  if (fullscreenVideo) return fullscreenVideo;

  if (platform === 'youtube') {
    const activeShort = document.querySelector<HTMLVideoElement>('ytd-reel-video-renderer[is-active] video');
    if (activeShort && location.pathname.startsWith('/shorts/')) return activeShort;
    const main = document.querySelector<HTMLVideoElement>('#movie_player video.html5-main-video');
    if (main) return main;
  }

  const playerVideo = document.querySelector<HTMLVideoElement>(`:is(${PLAYERS[platform]}) video`);
  return playerVideo ?? document.querySelector('video');
}

export function readPlayerTitle(platform: PlayerPlatform): string {
  return document.querySelector(TITLES[platform])?.textContent?.trim() ||
    document.title.replace(/\s*[-–—|_]\s*(?:YouTube|哔哩哔哩.*)$/iu, '').trim();
}

export function observePlayerUi(
  platform: PlayerPlatform,
  isVideoPage: () => boolean,
  openSidePanel: () => void,
): () => void {
  const host = document.createElement('span');
  const root = host.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = BUTTON_STYLES;
  const button = document.createElement('button');
  button.type = 'button';
  button.title = '打开小宇伴学';
  const dot = document.createElement('span');
  dot.className = 'brand-dot';
  dot.setAttribute('aria-hidden', 'true');
  button.append(dot, document.createTextNode('小宇伴学'));
  button.addEventListener('click', event => {
    event.stopPropagation();
    openSidePanel();
  });
  root.append(style, button);

  function mount() {
    if (!isVideoPage()) {
      host.remove();
      return;
    }
    const player = findPlayerVideo(platform)?.closest(PLAYERS[platform]);
    const controlsSelector = platform === 'bilibili'
      ? '.bpx-player-control-bottom-right'
      : '.ytp-right-controls';
    const controls = player?.querySelector(controlsSelector) ?? document.querySelector(controlsSelector);
    if (controls) {
      if (host.parentElement !== controls) controls.prepend(host);
      return;
    }

    const title = document.querySelector(TITLES[platform]);
    if (!title) host.remove();
    else if (title.nextElementSibling !== host) title.after(host);
  }

  let pendingFrame: number | undefined;
  const scheduleMount = () => {
    if (pendingFrame !== undefined) return;
    pendingFrame = window.requestAnimationFrame(() => {
      pendingFrame = undefined;
      mount();
    });
  };
  const observer = new MutationObserver(scheduleMount);
  observer.observe(document, { childList: true, subtree: true });
  window.addEventListener('popstate', scheduleMount);
  document.addEventListener('yt-navigate-finish', scheduleMount);
  mount();

  return () => {
    observer.disconnect();
    window.removeEventListener('popstate', scheduleMount);
    document.removeEventListener('yt-navigate-finish', scheduleMount);
    if (pendingFrame !== undefined) window.cancelAnimationFrame(pendingFrame);
    host.remove();
  };
}
