import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from 'tiptap-markdown'
import Placeholder from '@tiptap/extension-placeholder'
import Underline from '@tiptap/extension-underline'
import { 
  Bold, Italic, List, ListOrdered, 
  Heading1, Heading2, Quote, Code, Underline as UnderlineIcon,
  Undo, Redo
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface MarkdownEditorProps {
  content: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
}

const ToolbarButton = ({ onClick, isActive, children }: any) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      "p-2 rounded-lg transition-all active:scale-95",
      isActive 
        ? "bg-slate-900 text-white shadow-md dark:bg-white dark:text-black" 
        : "text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10"
    )}
  >
    {children}
  </button>
)

export const MarkdownEditor = ({ content, onChange, placeholder }: MarkdownEditorProps) => {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Underline,
      Markdown.configure({
        html: false,
        tightLists: true,
      }),
      Placeholder.configure({
        placeholder: placeholder || '在此输入内容，支持 Markdown 快捷键…',
      }),
    ],
    content: content ? content.replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&') : '',
    onUpdate: ({ editor }) => {
      const markdown = (editor.storage as any).markdown.getMarkdown();
      // Unescape common HTML entities that tiptap-markdown might escape
      const cleaned = markdown
        .replace(/&gt;/g, '>')
        .replace(/&lt;/g, '<')
        .replace(/&amp;/g, '&');
      onChange(cleaned)
    },
    editorProps: {
      attributes: {
        class: cn(
          "prose prose-slate dark:prose-invert max-w-none focus:outline-none min-h-[400px] p-10",
          "prose-headings:font-black prose-headings:tracking-tighter prose-headings:text-slate-900 dark:prose-headings:text-white",
          "prose-h1:text-2xl prose-h2:text-xl prose-h3:text-base",
          "prose-p:text-slate-600 dark:prose-p:text-slate-300 prose-p:leading-relaxed",
          "prose-blockquote:border-l-4 prose-blockquote:border-primary prose-blockquote:bg-slate-50 dark:prose-blockquote:bg-white/5 prose-blockquote:py-2 prose-blockquote:px-6 prose-blockquote:rounded-r-xl"
        ),
      },
    },
  })

  if (!editor) return null

  return (
    <div className="w-full flex flex-col rounded-2xl bg-white dark:bg-black/20 border border-slate-200 dark:border-white/5 shadow-sm overflow-hidden transition-all focus-within:shadow-lg focus-within:border-primary/20">
      <style>{`
        .ProseMirror {
          outline: none !important;
          min-height: 400px;
        }
        .ProseMirror h1 { font-size: 1.5rem; font-weight: 900; line-height: 1.2; margin-top: 1.5rem; margin-bottom: 0.75rem; tracking: -0.05em; }
        .ProseMirror h2 { font-size: 1.25rem; font-weight: 900; line-height: 1.3; margin-top: 1.25rem; margin-bottom: 0.5rem; }
        .ProseMirror h3 { font-size: 1rem; font-weight: 800; margin-top: 1rem; margin-bottom: 0.4rem; }
        .ProseMirror p { margin-bottom: 1.25rem; line-height: 1.7; font-size: 1rem; color: hsl(var(--muted-foreground)); }
        .ProseMirror ul { list-style-type: disc; padding-left: 1.5rem; margin-bottom: 1.25rem; }
        .ProseMirror ol { list-style-type: decimal; padding-left: 1.5rem; margin-bottom: 1.25rem; }
        .ProseMirror li { margin-bottom: 0.5rem; }
        .ProseMirror blockquote { border-left: 4px solid hsl(var(--primary)); padding-left: 1.5rem; font-style: italic; background: hsl(var(--unimind-bg-secondary)); padding-top: 0.5rem; padding-bottom: 0.5rem; margin-bottom: 1.25rem; border-radius: 0 0.75rem 0.75rem 0; }
        .ProseMirror code { background: hsl(var(--unimind-bg-secondary)); color: hsl(var(--primary)); padding: 0.2rem 0.4rem; border-radius: 0.375rem; font-family: monospace; font-size: 0.875rem; }
        .ProseMirror pre { background: hsl(var(--foreground)); color: hsl(var(--unimind-bg-secondary)); padding: 1.5rem; border-radius: 1rem; font-family: monospace; margin-bottom: 1.25rem; }
        .ProseMirror pre code { background: transparent; color: inherit; padding: 0; }
        
        .dark .ProseMirror h1, .dark .ProseMirror h2, .dark .ProseMirror h3 { color: white; }
        .dark .ProseMirror p { color: hsl(var(--muted-foreground)); }
        .dark .ProseMirror blockquote { background: rgba(255,255,255,0.05); }
        .dark .ProseMirror code { background: rgba(255,255,255,0.1); }

        .ProseMirror p.is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          float: left;
          color: hsl(var(--muted-foreground));
          pointer-events: none;
          height: 0;
        }
      `}</style>

      {/* Professional Fixed Toolbar */}
      <div className="flex items-center flex-wrap gap-1 p-2 px-4 border-b border-slate-100 dark:border-white/5 bg-slate-50/50 dark:bg-white/5 backdrop-blur-md">
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleBold().run()} 
          isActive={editor.isActive('bold')}
        >
          <Bold className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleItalic().run()} 
          isActive={editor.isActive('italic')}
        >
          <Italic className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleUnderline().run()} 
          isActive={editor.isActive('underline')}
        >
          <UnderlineIcon className="w-4 h-4" />
        </ToolbarButton>
        
        <div className="w-px h-6 bg-slate-200 dark:bg-white/10 mx-2" />
        
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} 
          isActive={editor.isActive('heading', { level: 1 })}
        >
          <Heading1 className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} 
          isActive={editor.isActive('heading', { level: 2 })}
        >
          <Heading2 className="w-4 h-4" />
        </ToolbarButton>
        
        <div className="w-px h-6 bg-slate-200 dark:bg-white/10 mx-2" />
        
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleBulletList().run()} 
          isActive={editor.isActive('bulletList')}
        >
          <List className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleOrderedList().run()} 
          isActive={editor.isActive('orderedList')}
        >
          <ListOrdered className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleBlockquote().run()} 
          isActive={editor.isActive('blockquote')}
        >
          <Quote className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton 
          onClick={() => editor.chain().focus().toggleCodeBlock().run()} 
          isActive={editor.isActive('codeBlock')}
        >
          <Code className="w-4 h-4" />
        </ToolbarButton>

        <div className="flex-1" />

        <ToolbarButton onClick={() => editor.chain().focus().undo().run()}>
          <Undo className="w-4 h-4" />
        </ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().redo().run()}>
          <Redo className="w-4 h-4" />
        </ToolbarButton>
      </div>
      
      {/* Editor Surface */}
      <div className="relative">
        <EditorContent editor={editor} />
      </div>
    </div>
  )
}
