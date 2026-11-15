import { t, useLocale } from '@/i18n';
import { Component, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return <ErrorFallback error={this.state.error} onReset={this.handleReset} />;
    }
    return this.props.children;
  }
}

export function ErrorFallback({ error, onReset }: { error: Error | null; onReset: () => void }) {
  useLocale();
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-sm w-full text-center space-y-4">
        <div className="w-14 h-14 rounded-full bg-destructive/10 flex items-center justify-center mx-auto">
          <span className="text-2xl">!</span>
        </div>
        <div>
          <h2 className="text-lg font-bold text-foreground">{t('页面出错了')}</h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t(error?.message || '发生了未知错误')}
          </p>
          <p className="mt-2 text-xs italic text-muted-foreground">{t('别慌，宇宙偶尔也会出点小差错。——《银河搭车客指南》')}</p>
        </div>
        <div className="flex gap-2 justify-center">
          <Button variant="outline" onClick={() => window.location.href = '/'}>
            {t('回到首页')}</Button>
          <Button onClick={onReset}>
            {t('重试')}</Button>
        </div>
      </div>
    </div>
  );
}
