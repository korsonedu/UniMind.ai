import { Link } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';

export default function NotFound() {
  return (
    <PageWrapper title="404" subtitle="页面不存在">
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-6xl font-bold text-muted-foreground/30">404</p>
        <p className="mt-4 text-lg text-muted-foreground">您访问的页面不存在或已被移除。</p>
        <Link
          to="/"
          className="mt-6 inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          返回首页
        </Link>
      </div>
    </PageWrapper>
  );
}
