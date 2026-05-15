# UniMind.ai Frontend

React 19 + TypeScript + Vite + Tailwind CSS 4 + shadcn/ui

## 快速开始

```bash
npm install
npm run dev        # Vite HMR 开发服务器
npm run build      # 生产构建 → dist/
```

## 技术栈

- **框架**: React 19 + TypeScript
- **构建**: Vite
- **样式**: Tailwind CSS 4 + shadcn/ui (Radix)
- **状态管理**: Zustand 5
- **路由**: React Router 6
- **数学渲染**: KaTeX + remark-math + rehype-katex
- **富文本**: TipTap + react-markdown
- **图表**: Recharts 3
- **国际化**: i18next (中英双语)

## 项目结构

```
src/
├── pages/          # 21 页面组件
├── components/     # 通用组件 + shadcn/ui
├── lib/            # API 客户端、权限检查、通用 hooks
├── store/          # Zustand stores
└── i18n/           # 国际化资源
```

## 环境变量

```bash
VITE_API_URL=http://localhost:8000   # 后端 API 地址
```
