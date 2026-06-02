import { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import api from '@/lib/api';
import { PageWrapper } from '@/components/PageWrapper';

interface LegalDoc {
  doc_type: string;
  doc_type_display: string;
  version: string;
  title: string;
  content: string;
  effective_date: string;
}

export default function Legal() {
  const location = useLocation();
  const docType = location.pathname.includes('privacy') ? 'privacy' : 'terms';
  const [doc, setDoc] = useState<LegalDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    api.get(`/legal/${docType}/`)
      .then(r => setDoc(r.data))
      .catch(() => setError('文档加载失败'))
      .finally(() => setLoading(false));
  }, [docType]);

  if (loading) {
    return (
      <PageWrapper title="加载中...">
        <div className="max-w-3xl mx-auto py-12 text-center text-muted-foreground">加载中...</div>
      </PageWrapper>
    );
  }

  if (error || !doc) {
    return (
      <PageWrapper title="错误">
        <div className="max-w-3xl mx-auto py-12 text-center text-muted-foreground">
          {error || '文档不存在'}
          <div className="mt-4"><Link to="/" className="text-primary underline">返回首页</Link></div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title={doc.title}>
      <article className="prose prose-slate max-w-3xl mx-auto py-8">
        <p className="text-muted-foreground">
          版本：{doc.version} &nbsp;|&nbsp; 生效日期：{doc.effective_date}
        </p>
        <div dangerouslySetInnerHTML={{ __html: doc.content }} />
        <div className="mt-8 pt-4 border-t text-sm text-muted-foreground">
          <Link to="/privacy" className={docType === 'privacy' ? 'font-bold' : 'underline'}>隐私政策</Link>
          {' · '}
          <Link to="/terms" className={docType === 'terms' ? 'font-bold' : 'underline'}>用户协议</Link>
        </div>
      </article>
    </PageWrapper>
  );
}
