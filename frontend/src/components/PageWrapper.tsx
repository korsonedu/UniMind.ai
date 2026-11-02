import { useEffect } from 'react';
import { useSystemStore } from '@/store/useSystemStore';

interface PageWrapperProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export const PageWrapper = ({ children, title, subtitle, action }: PageWrapperProps) => {
  const setPageHeader = useSystemStore(state => state.setPageHeader);

  useEffect(() => {
    setPageHeader(title ?? '', subtitle ?? '');
    return () => setPageHeader('', '');
  }, [title, subtitle, setPageHeader]);

  return (
    <div className="um-page-wrapper w-full space-y-4 um-motion-surface animate-in fade-in duration-[180ms] ease-out">
      {action && (
        <div className="um-page-actions flex justify-end pb-2">
          {action}
        </div>
      )}
      <div className="pt-0">
        {children}
      </div>
    </div>
  );
};
