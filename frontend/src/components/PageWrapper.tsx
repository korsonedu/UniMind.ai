import { useEffect } from 'react';
import { useSystemStore } from '@/store/useSystemStore';

export const PageWrapper = ({ children, title, subtitle, action }: any) => {
  const setPageHeader = useSystemStore(state => state.setPageHeader);

  useEffect(() => {
    setPageHeader(title, subtitle);
    return () => setPageHeader('', '');
  }, [title, subtitle, setPageHeader]);

  return (
    <div className="w-full space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {action && (
        <div className="flex justify-end pb-2">
          {action}
        </div>
      )}
      <div className="pt-0">
        {children}
      </div>
    </div>
  );
};
