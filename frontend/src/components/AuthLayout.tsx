import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from '@phosphor-icons/react';
import '@/styles/auth.css';

interface AuthLayoutProps {
  children: ReactNode;
  title: string;
  subtitle?: ReactNode;
  footer?: ReactNode;
}

export const AuthLayout = ({ children, title, subtitle, footer }: AuthLayoutProps) => (
  <div className={`um-auth-shell${window.unimindDesktop ? ' um-auth-native' : ''}`}>
    <header className="um-auth-topbar">
      <Link to="/" className="um-auth-wordmark" aria-label="UniMind.ai 首页">UniMind<span>.ai</span></Link>
      {!window.unimindDesktop && <Link to="/" className="um-auth-home"><ArrowLeft size={16} aria-hidden="true" />返回首页</Link>}
    </header>
    <main className="um-auth-main">
      <section className="um-auth-panel" aria-labelledby="auth-title">
        <div className="um-auth-mark"><img src="/unimind_logo_small.png" alt="" width="56" height="56" /></div>
        <h1 id="auth-title">{title}</h1>
        {subtitle && <p className="um-auth-subtitle">{subtitle}</p>}
        <div className="um-auth-fields">{children}</div>
        {footer && <div className="um-auth-footer">{footer}</div>}
      </section>
    </main>
    <footer className="um-auth-legal">
      <Link to="/terms" target={window.unimindDesktop ? '_blank' : undefined}>用户协议</Link>
      <span aria-hidden="true">·</span>
      <Link to="/privacy" target={window.unimindDesktop ? '_blank' : undefined}>隐私政策</Link>
    </footer>
  </div>
);
