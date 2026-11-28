import type { ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from '@phosphor-icons/react';
import { t } from '@/i18n';
import { SpaceSwitcher } from './SpaceSwitcher';

/** Crisp flomo-inspired two-line drawer trigger icon (delicate 1.55px stroke). */
export function MobileMenuIcon({ size = 19 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
      <path d="M3 6.8H17" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" />
      <path d="M3 13.2H13.2" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" />
    </svg>
  );
}

/** Compact UniMind brand mark for mobile hero / empty states. */
export function UniMindBrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="um-mobile-brand-grad" gradientUnits="userSpaceOnUse" x1="15" y1="90" x2="90" y2="10">
          <stop stopColor="#4f5fa6" />
          <stop offset="0.55" stopColor="#5b6dc2" />
          <stop offset="1" stopColor="#7c8ce0" />
        </linearGradient>
      </defs>
      <g fill="url(#um-mobile-brand-grad)">
        <path
          d="M18 36C18 13 48 13 48 36C48 13 78 13 78 36V61C78 79 67 89 48 89S18 79 18 61Z"
          fill="none"
          stroke="url(#um-mobile-brand-grad)"
          strokeWidth="12"
          strokeLinejoin="round"
        />
        <rect x="33" y="48" width="8" height="13" rx="4" />
        <rect x="56" y="48" width="8" height="13" rx="4" />
        <circle cx="90" cy="14" r="5" />
      </g>
    </svg>
  );
}

export interface MobileNavigationSlot {
  onOpen: () => void;
  links: ReactNode;
  account: ReactNode;
}

interface GlobalMobileDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  links: ReactNode;
  account: ReactNode;
}

/** Shared left drawer used on top-level mobile pages outside XiaoYu. */
export function GlobalMobileDrawer({ open, onOpenChange, links, account }: GlobalMobileDrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <button type="button" className="um-mobile-menu-trigger" aria-label={t('应用导航')}>
          <MobileMenuIcon size={20} />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="um-m-drawer-overlay" />
        <Dialog.Content className="um-m-drawer">
          <Dialog.Title className="sr-only">{t('应用导航')}</Dialog.Title>
          <Dialog.Description className="sr-only">{t('切换学习空间或模块。')}</Dialog.Description>
          <div className="um-m-drawer-head">
            <SpaceSwitcher />
            <Dialog.Close asChild>
              <button type="button" className="um-m-drawer-close" aria-label={t('关闭侧栏')}>
                <X size={18} />
              </button>
            </Dialog.Close>
          </div>
          <div onClick={event => { if ((event.target as HTMLElement).closest('a')) onOpenChange(false); }}>
            {links}
          </div>
          <div className="um-m-drawer-body" />
          <div className="um-m-drawer-footer" onClick={event => { if ((event.target as HTMLElement).closest('a')) onOpenChange(false); }}>
            {account}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
