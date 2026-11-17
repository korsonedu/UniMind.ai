import { t, useLocale } from '@/i18n';
import React from 'react';
import { Joyride, STATUS } from 'react-joyride';
import type { Step, EventData } from 'react-joyride';

export interface TourStep {
  target: string;
  title: string;
  content: string;
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'auto';
  width?: number;
}

interface GuidedTourProps {
  steps: TourStep[];
  onDismiss: () => void;
}

const BRAND_BLUE = '#0071E3';

const GuidedTour: React.FC<GuidedTourProps> = ({ steps, onDismiss }) => {
  useLocale();
  const handleEvent = (data: EventData) => {
    if (data.status === STATUS.FINISHED || data.status === STATUS.SKIPPED) {
      onDismiss();
    }
  };

  return (
    <Joyride
      steps={steps as Step[]}
      run
      continuous
      scrollToFirstStep
      options={{
        primaryColor: BRAND_BLUE,
        backgroundColor: 'hsl(var(--popover))',
        arrowColor: 'hsl(var(--popover))',
        textColor: 'hsl(var(--popover-foreground))',
        zIndex: 10000,
        showProgress: true,
        skipBeacon: true,
        buttons: ['back', 'close', 'primary', 'skip'],
        closeButtonAction: 'skip',
      }}
      onEvent={handleEvent}
      locale={{
        back: t('上一步'),
        close: t('关闭'),
        last: t('完成'),
        next: t('下一步'),
        nextWithProgress: t('下一步 ({current}/{total})'),
      }}
      styles={{
        tooltip: {
          borderRadius: '1rem',
          padding: '1.25rem',
          boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
        },
        tooltipTitle: {
          fontSize: '1.125rem',
          fontWeight: 700,
        },
        tooltipContent: {
          fontSize: '0.875rem',
          color: 'hsl(var(--muted-foreground))',
          paddingTop: '0.25rem',
        },
        buttonPrimary: {
          color: '#fff',
          borderRadius: '0.75rem',
          padding: '0.5rem 1rem',
          fontSize: '0.8125rem',
          fontWeight: 600,
        },
        buttonBack: {
          borderRadius: '0.75rem',
          padding: '0.5rem 1rem',
          fontSize: '0.8125rem',
          fontWeight: 600,
          color: 'hsl(var(--muted-foreground))',
        },
        buttonSkip: {
          color: 'hsl(var(--muted-foreground))',
          fontSize: '0.8125rem',
          fontWeight: 500,
        },
        overlay: {
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
        },
      }}
    />
  );
};

export default GuidedTour;
