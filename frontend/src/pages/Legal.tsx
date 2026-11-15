import { t, useLocale } from '@/i18n';
import { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import DOMPurify from 'dompurify';
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
  const locale = useLocale();
  const location = useLocation();
  const docType = location.pathname.includes('privacy') ? 'privacy' : 'terms';
  const [doc, setDoc] = useState<LegalDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [loadingDocType, setLoadingDocType] = useState(docType);
  if (loadingDocType !== docType) {
    setLoadingDocType(docType);
    setLoading(true); setError('');
  }

  useEffect(() => {
    api.get(`/legal/${docType}/`)
      .then(r => { setDoc(r.data); setError(''); })
      .catch(() => setError(t('文档加载失败')))
      .finally(() => setLoading(false));
  }, [docType]);

  if (loading) {
    return (
      <PageWrapper title={t('加载中...')}>
        <div className="max-w-3xl mx-auto py-12 text-center text-muted-foreground">{t('加载中...')}</div>
      </PageWrapper>
    );
  }

  if (error || !doc) {
    return (
      <PageWrapper title={t('错误')}>
        <div className="max-w-3xl mx-auto py-12 text-center text-muted-foreground">
          {error || t('文档不存在')}
          <div className="mt-4"><Link to="/" className="text-primary underline">{t('返回首页')}</Link></div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title={t(doc.title)}>
      <article className="prose prose-slate max-w-3xl mx-auto py-8">
        {locale === 'en' && <p className="text-muted-foreground">{t('正文按发布时的原语言展示。')}</p>}
        <p className="text-muted-foreground">
          {t('版本：')}{doc.version} {' | '}{t('生效日期：')}{doc.effective_date}
        </p>
        <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(doc.content) }} />
        <div className="mt-8 pt-4 border-t text-sm text-muted-foreground">
          <Link to="/privacy" className={docType === 'privacy' ? 'font-bold' : 'underline'}>{t('隐私政策')}</Link>
          {' · '}
          <Link to="/terms" className={docType === 'terms' ? 'font-bold' : 'underline'}>{t('用户协议')}</Link>
        </div>
      </article>
    </PageWrapper>
  );
}
