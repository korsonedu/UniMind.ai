import type { WorkbenchArticle } from '../shared/types';

// Chrome serializes this function when injecting it into the active tab.
export function extractWorkbenchArticle(maxCharacters: number): WorkbenchArticle & { pageUrl: string } {
  const omitted = [
    'script', 'style', 'nav', 'footer', 'aside', 'noscript', 'template', 'iframe', 'svg', 'form',
    '[hidden]', '[aria-hidden="true"]', '[inert]', '[role="navigation"]', '[role="contentinfo"]',
    '[role="banner"]', '[role="complementary"]', '[data-ad]', '[data-ad-slot]', '.ad', '.ads',
    '.advertisement', '.ad-banner', 'details:not([open]) > :not(summary)',
  ].join(',');
  const visibility = new WeakMap<Element, boolean>();
  function visible(element: Element): boolean {
    const cached = visibility.get(element);
    if (cached !== undefined) return cached;
    const style = getComputedStyle(element);
    const result = !element.matches(omitted) && style.display !== 'none' && style.visibility !== 'hidden'
      && style.visibility !== 'collapse' && style.contentVisibility !== 'hidden' && style.opacity !== '0'
      && (!element.parentElement || visible(element.parentElement));
    visibility.set(element, result);
    return result;
  }

  const firstVisible = (selector: string, root: ParentNode = document) =>
    Array.from(root.querySelectorAll(selector)).find(visible);
  const main = firstVisible('main, [role="main"]');
  const root = main ?? firstVisible('article') ?? document.body;
  const squash = (value: string) => value.replace(/\s+/gu, ' ').trim();
  function textOf(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue ?? '';
    if (!(node instanceof Element) || !visible(node)) return '';
    if (node.tagName === 'BR') return '\n';
    return Array.from(node.childNodes, textOf).join('');
  }

  const title = squash(
    textOf(firstVisible('h1', root ?? document) ?? document.createTextNode(''))
    || document.querySelector('meta[property="og:title"]')?.getAttribute('content')
    || document.title || location.hostname,
  ) || location.hostname;
  const pageUrl = new URL(location.href);
  pageUrl.hash = '';
  const canonical = document.querySelector('link[rel~="canonical" i]')?.getAttribute('href')?.trim();
  let url = pageUrl.href;
  if (canonical) {
    try {
      const candidate = new URL(canonical, document.baseURI);
      candidate.hash = '';
      if (/^https?:$/.test(candidate.protocol) && !candidate.username && !candidate.password
          && candidate.href.length <= 3000) url = candidate.href;
    } catch { /* Keep the current URL when the canonical link is invalid. */ }
  }

  const blocks: string[] = [];
  let length = 0;
  let finished = false;
  let parts: string[] = [];
  let prefix = '';
  const lists: { next: number | null }[] = [];
  function append(text: string, fence = '') {
    if (!text) return;
    const room = maxCharacters - length - (blocks.length ? 2 : 0) - (fence ? 2 * fence.length + 2 : 0);
    if (room <= 0) { finished = true; return; }
    if (text.length > room) {
      text = text.slice(0, room).replace(/[\uD800-\uDBFF]$/u, '').trimEnd();
      const boundary = fence ? text.lastIndexOf('\n') : text.lastIndexOf(' ');
      if (boundary > room * 0.9) text = text.slice(0, boundary);
      finished = true;
    }
    const block = fence ? `${fence}\n${text}\n${fence}` : text;
    blocks.push(block);
    length += block.length + (blocks.length > 1 ? 2 : 0);
  }
  function flush() {
    const text = parts.join('').split('\n').map(squash).join('\n').trim();
    parts = [];
    if (!text) return;
    append(prefix + text);
    prefix = '';
  }
  function walk(node: Node) {
    if (finished) return;
    if (node.nodeType === Node.TEXT_NODE) {
      parts.push((node.nodeValue ?? '').replace(/\s+/gu, ' '));
      return;
    }
    if (!(node instanceof Element) || !visible(node)) return;
    const tag = node.tagName;
    if (tag === 'BR') { parts.push('\n'); return; }
    const list = tag === 'UL' || tag === 'OL';
    const heading = /^H[1-3]$/.test(tag);
    const block = heading || list || /^(P|DIV|SECTION|ARTICLE|MAIN|BLOCKQUOTE|LI|PRE|TR|DT|DD)$/.test(tag);
    if (block) flush();
    if (tag === 'PRE') {
      const code = textOf(node).replace(/^\n|\n$/g, '');
      let ticks = 2;
      for (const run of code.matchAll(/`+/g)) ticks = Math.max(ticks, run[0].length);
      append(code, '`'.repeat(ticks + 1));
      return;
    }
    if (list) lists.push({ next: tag === 'OL' ? (node as HTMLOListElement).start : null });
    const currentList = lists.at(-1);
    if (tag === 'LI' && currentList) {
      const marker = currentList.next === null ? '-' : `${currentList.next++}.`;
      prefix = `${'    '.repeat(lists.length - 1)}${marker} `;
    } else if (heading) {
      prefix = `${'#'.repeat(Number(tag[1]))} `;
    }
    for (const child of node.childNodes) {
      walk(child);
      if (finished) break;
    }
    if (block && !finished) flush();
    if (heading || tag === 'LI') prefix = '';
    if (list) lists.pop();
  }
  if (root) walk(root);
  if (!finished) flush();
  return { title, url, content: blocks.join('\n\n'), pageUrl: pageUrl.href };
}
