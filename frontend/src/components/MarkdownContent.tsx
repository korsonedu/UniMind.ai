import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface Props {
  content: string;
  className?: string;
  /** 额外的 remark 插件 */
  extraRemarkPlugins?: any[];
  /** 额外的 rehype 插件 */
  extraRehypePlugins?: any[];
  /** 自定义组件覆盖（如图片渲染） */
  components?: Record<string, any>;
}

/**
 * Markdown 渲染包装组件。
 * 内置 remarkMath + remarkGfm + rehypeKatex，消除项目中重复的 react-markdown 配置。
 */
export function MarkdownContent({
  content,
  className,
  extraRemarkPlugins,
  extraRehypePlugins,
  components,
}: Props) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm, ...(extraRemarkPlugins || [])]}
        rehypePlugins={[rehypeKatex, ...(extraRehypePlugins || [])]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
