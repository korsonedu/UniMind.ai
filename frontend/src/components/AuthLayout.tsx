import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

interface AuthLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle?: React.ReactNode;
  /** Footer line displayed below the form, e.g. "没有账号？注册" */
  footer?: React.ReactNode;
}

export const AuthLayout: React.FC<AuthLayoutProps> = ({ children, title, subtitle, footer }) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 60);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-[1.05fr_1fr]">
      {/* ── Left Brand Panel ── */}
      <div
        ref={panelRef}
        className="
          relative hidden lg:flex flex-col items-center justify-center overflow-hidden
          bg-gradient-to-br from-[#e8effb] via-[#f0f4ff] to-[#f5f7ff]
          dark:bg-gradient-to-br dark:from-[#080c1a] dark:via-[#0d1117] dark:to-[#0a0f1a]
        "
      >
        {/* Dot-grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.14] dark:opacity-[0.09]"
          style={{
            backgroundImage: `radial-gradient(circle, #0071E3 0.7px, transparent 0.7px)`,
            backgroundSize: '20px 20px',
          }}
        />

        {/* Large ambient glow orbs */}
        <div className="absolute -top-32 -left-32 w-[500px] h-[500px] rounded-full bg-[#0071E3]/[0.05] dark:bg-[#3395ff]/[0.06] blur-[80px]" />
        <div className="absolute -bottom-40 -right-40 w-[560px] h-[560px] rounded-full bg-[#0071E3]/[0.04] dark:bg-[#3395ff]/[0.05] blur-[100px]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] rounded-full bg-[#0071E3]/[0.03] dark:bg-[#3395ff]/[0.04] blur-[60px]" />

        {/* Content */}
        <div className="relative z-10 flex flex-col items-center gap-8 px-12 text-center max-w-[360px]">
          <img
            src="/unimind_logo_small.png"
            alt="UniMind"
            className="h-10 w-auto drop-shadow-sm"
          />

          <div className="space-y-4">
            <h2 className="text-[22px] font-bold tracking-tight text-[#1D1D1F] dark:text-white leading-snug">
              AI 驱动的新一代
              <br />
              智能学习平台
            </h2>
            <p className="text-[14px] leading-relaxed text-[#6E6E73] dark:text-white/40">
              知识图谱 × 自适应记忆 × 智能教练
              <br />
              为每个学习者量身定制
            </p>
          </div>

          {/* Subtle feature dots */}
          <div className="flex gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#0071E3]/30 dark:bg-[#3395ff]/30" />
            <span className="w-1.5 h-1.5 rounded-full bg-[#0071E3]/20 dark:bg-[#3395ff]/20" />
            <span className="w-1.5 h-1.5 rounded-full bg-[#0071E3]/10 dark:bg-[#3395ff]/10" />
          </div>
        </div>
      </div>

      {/* ── Right Form Panel ── */}
      <div className="flex flex-col items-center justify-center bg-white dark:bg-black px-6 py-12 lg:px-16 lg:py-16">
        <div className="w-full max-w-[400px]">
          {/* Mobile-only logo */}
          <div className="lg:hidden flex flex-col items-center gap-4 mb-10">
            <img
              src="/unimind_logo_small.png"
              alt="UniMind"
              className="h-7 w-auto"
            />
          </div>

          {/* Header */}
          <div
            className="space-y-1.5 mb-8"
            style={{
              opacity: visible ? 1 : 0,
              transform: visible ? 'translateY(0)' : 'translateY(12px)',
              transition: 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            <h1 className="text-[26px] font-bold tracking-tight text-[#1D1D1F] dark:text-white">
              {title}
            </h1>
            {subtitle && (
              <p className="text-[14px] text-[#6E6E73] dark:text-white/45 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>

          {/* Form content */}
          <div
            style={{
              opacity: visible ? 1 : 0,
              transform: visible ? 'translateY(0)' : 'translateY(16px)',
              transition: 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.1s, transform 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.1s',
            }}
          >
            {children}
          </div>

          {/* Footer */}
          {footer && (
            <div
              className="mt-8 text-center"
              style={{
                opacity: visible ? 1 : 0,
                transition: 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.25s',
              }}
            >
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
