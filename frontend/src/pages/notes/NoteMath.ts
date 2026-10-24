import { InputRule, Node } from '@tiptap/core';
import type { Node as ProseMirrorNode } from '@tiptap/pm/model';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface MathToken { content: string; markup: string }
interface InlineState {
  src: string; pos: number; posMax: number;
  push: (type: string, tag: string, nesting: number) => MathToken;
}
interface MarkdownParser {
  inline: { ruler: { before: (before: string, name: string, rule: (state: InlineState, silent: boolean) => boolean) => void } };
  renderer: { rules: Record<string, (tokens: MathToken[], index: number) => string> };
  utils: { escapeHtml: (text: string) => string };
}

// Keep LaTeX out of Markdown's ordinary text escaping during rich-text edits.
export const NoteMath = Node.create({
  name: 'noteMath', group: 'inline', inline: true, atom: true,
  addAttributes() {
    return {
      latex: { default: '', parseHTML: element => element.getAttribute('data-latex') },
      delimiter: { default: '$', parseHTML: element => element.getAttribute('data-delimiter') || '$' },
    };
  },
  parseHTML() { return [{ tag: 'span[data-note-math]' }]; },
  renderHTML({ node }) {
    return ['span', { 'data-note-math': '', 'data-latex': node.attrs.latex, 'data-delimiter': node.attrs.delimiter, class: 'notes-math' }, `${node.attrs.delimiter}${node.attrs.latex}${node.attrs.delimiter}`];
  },
  renderText({ node }) { return `${node.attrs.delimiter}${node.attrs.latex}${node.attrs.delimiter}`; },
  addNodeView() {
    return ({ node }) => {
      const dom = document.createElement('span');
      dom.className = 'notes-math';
      dom.contentEditable = 'false';
      katex.render(node.attrs.latex, dom, { throwOnError: false, displayMode: node.attrs.delimiter === '$$' });
      return { dom };
    };
  },
  addInputRules() {
    return [new InputRule({
      find: /(\${1,2})([^$\n]+)\1$/,
      handler: ({ state, range, match }) => { state.tr.replaceWith(range.from, range.to, this.type.create({ latex: match[2], delimiter: match[1] })); },
    })];
  },
  addStorage() {
    return { markdown: {
      serialize(state: { write: (text: string) => void }, node: ProseMirrorNode) {
        state.write(`${node.attrs.delimiter}${node.attrs.latex}${node.attrs.delimiter}`);
      },
      parse: { setup(parser: MarkdownParser) {
        if (parser.renderer.rules.note_math) return;
        parser.inline.ruler.before('escape', 'note_math', (state, silent) => {
          if (state.src[state.pos] !== '$') return false;
          const delimiter = state.src.startsWith('$$', state.pos) ? '$$' : '$';
          const start = state.pos + delimiter.length;
          let end = state.src.indexOf(delimiter, start);
          while (end > 0 && state.src[end - 1] === '\\') end = state.src.indexOf(delimiter, end + delimiter.length);
          if (end <= start || end >= state.posMax) return false;
          if (!silent) { const token = state.push('note_math', '', 0); token.content = state.src.slice(start, end); token.markup = delimiter; }
          state.pos = end + delimiter.length;
          return true;
        });
        parser.renderer.rules.note_math = (tokens, index) => {
          const token = tokens[index];
          return `<span data-note-math data-latex="${parser.utils.escapeHtml(token.content)}" data-delimiter="${token.markup}">${parser.utils.escapeHtml(token.markup + token.content + token.markup)}</span>`;
        };
      } },
    } };
  },
});
