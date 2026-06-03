import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ArrowLeft, ArrowRight, Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { APP_VERSION, COPYRIGHT_YEAR, COPYRIGHT_ENTITY } from '@/constants/version';
import { useTranslation } from 'react-i18next';

const PricingPage: React.FC = () => {
  const { t } = useTranslation('landing');
  const navigate = useNavigate();
  const [annual, setAnnual] = useState(true);

  const plans = t('pricing.plans', { returnObjects: true }) as Array<{ label: string; desc: string; persona?: string; cta: string; features: string[] }>;
  const prices = [
    { monthly: '¥0', yearly: '¥0' },
    { monthly: '¥499', yearly: '¥416' },
    { monthly: '¥1,299', yearly: '¥1,083' },
    { monthly: '¥3,999', yearly: '¥3,333' },
  ];
  const popularIdx = 2;

  return (
    <div className="min-h-screen font-sans antialiased" style={{ background: '#0a0a0d', color: '#f0f0ed' }}>
      {/* Ambient bg */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 0 }}>
        <div className="absolute top-1/4 -left-32 w-[500px] h-[500px] rounded-full blur-[120px] opacity-[0.06]" style={{ background: '#5b5fef' }} />
        <div className="absolute bottom-1/4 -right-32 w-[400px] h-[400px] rounded-full blur-[100px] opacity-[0.04]" style={{ background: '#38bdf8' }} />
      </div>

      <div className="relative z-10">
        {/* Nav */}
        <nav className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="flex items-center gap-2">
            <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
            <span className="font-bold text-base tracking-tight text-white">UniMind</span>
          </button>
          <button onClick={() => navigate('/')} className="inline-flex items-center gap-1.5 text-sm font-medium text-white/60 hover:text-white transition-colors">
            <ArrowLeft className="h-3.5 w-3.5" />
            {t('pricing.backHome')}
          </button>
        </nav>

        {/* Header */}
        <section className="py-16 md:py-24 text-center px-6">
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight text-white max-w-3xl mx-auto leading-[1.08]">
            {t('pricing.pageTitle')}
          </h1>
          <p className="mt-5 text-base md:text-lg max-w-xl mx-auto leading-relaxed text-white/65">
            {t('pricing.pageSubtitle')}
          </p>

          {/* Trial banner removed — moved below pricing grid */}
        </section>

        {/* Toggle */}
        <section className="max-w-6xl mx-auto px-6 pb-8">
          <div className="flex items-center justify-center gap-3">
            <span className={cn('text-sm font-semibold', annual ? 'text-white/50' : 'text-white')}>
              {t('pricing.monthly')}
            </span>
            <button
              onClick={() => setAnnual(!annual)}
              className="w-11 h-6 rounded-full transition-all relative"
              style={{ background: annual ? '#5b5fef' : '#333' }}
            >
              <div className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', annual ? 'left-[22px]' : 'left-0.5')} />
            </button>
            <span className={cn('text-sm font-semibold flex items-center gap-1.5', annual ? 'text-white' : 'text-white/50')}>
              {t('pricing.annually')}
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80' }}>{t('pricing.saveBadge')}</span>
            </span>
          </div>
        </section>

        {/* Plans */}
        <section className="max-w-6xl mx-auto px-6 pb-24">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-stretch">
            {plans.map((plan, pi) => {
              const isFree = prices[pi].monthly === '¥0';
              const price = annual && !isFree ? prices[pi].yearly : prices[pi].monthly;
              const isPopular = pi === popularIdx;
              const isPro = pi === 3;

              return (
                <div
                  key={plan.label}
                  className={cn('p-6 rounded-2xl border flex flex-col', isPopular && 'ring-1')}
                  style={{
                    borderColor: isPopular ? 'rgba(91,95,239,0.4)' : 'rgba(255,255,255,0.06)',
                    background: isPopular ? 'rgba(91,95,239,0.06)' : 'rgba(255,255,255,0.02)',
                    ...(isPopular ? { boxShadow: '0 0 40px rgba(91,95,239,0.08)' } : {}),
                  }}
                >
                  <div className="mb-5" style={{ minHeight: '100px' }}>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-bold text-base text-white">{plan.label}</h3>
                      {isPopular && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: '#5b5fef' }}>
                          {t('pricing.popularBadge')}
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] text-white/55">{plan.desc}</p>
                    {plan.persona && <p className="text-[11px] mt-1.5 leading-relaxed text-white/45 line-clamp-2">{plan.persona}</p>}
                  </div>

                  <div className="mb-5" style={{ minHeight: '62px' }}>
                    <div className="flex items-baseline gap-1">
                      <span className="text-3xl font-bold tracking-tight text-white" style={{ fontFamily: '"DM Mono", monospace' }}>
                        {price}
                      </span>
                      {!isFree && <span className="text-sm text-white/55">{t('pricing.perMonth')}</span>}
                    </div>
                    <p className="text-[11px] mt-1 h-4" style={{ color: isFree ? '#4ade80' : 'rgba(255,255,255,0.45)' }}>
                      {!isFree && annual ? `${t('pricing.annualTotal')}${parseInt(prices[pi].yearly.replace('¥', '').replace(',', '')) * 12}` : isFree ? t('pricing.freeForever') : ''}
                    </p>
                  </div>

                  <Button
                    className="w-full h-10 rounded-xl text-sm font-bold mb-5"
                    style={isPopular
                      ? { background: '#5b5fef', color: '#fff' }
                      : isPro
                        ? { background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }
                        : { background: 'rgba(255,255,255,0.04)', color: '#fff' }
                    }
                    onClick={() => {
                      if (isPro) {
                        document.querySelector('#pricing-faq')?.scrollIntoView({ behavior: 'smooth' });
                      } else {
                        navigate('/register');
                      }
                    }}
                  >
                    {isPopular && <Sparkles className="h-3.5 w-3.5 mr-1.5" />}
                    {plan.cta}
                  </Button>

                  <ul className="space-y-2 flex-1">
                    {plan.features.map((f, fi) => (
                      <li key={fi} className="flex items-start gap-2 text-[12px]" style={{ color: 'rgba(255,255,255,0.7)' }}>
                        <Check className="h-3.5 w-3.5 shrink-0 mt-0.5 text-green-400" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
          <p className="text-center mt-8 text-xs text-white/40">{t('pricing.footer')}</p>

          {/* Trial info — plain text, no card */}
          <div className="max-w-2xl mx-auto mt-8 text-center space-y-2">
            <p className="text-sm font-semibold text-white/80">{t('pricing.trialTitle')}</p>
            <p className="text-[13px] leading-relaxed text-white/50">{t('pricing.trialDesc')}</p>
          </div>
        </section>

        {/* FAQ */}
        <section id="pricing-faq" className="max-w-3xl mx-auto px-6 pb-24">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-center mb-10 text-white">{t('faq.label')}</h2>
          <div className="space-y-2">
            {(t('faq.items', { returnObjects: true }) as Array<{ q: string; a: string }>).filter((_, i) => [0, 4, 5, 7].includes(i)).map((faq, i) => (
              <div key={i} className="rounded-xl border p-5" style={{ borderColor: 'rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
                <p className="font-semibold text-sm text-white mb-2">{faq.q}</p>
                <p className="text-sm leading-relaxed text-white/65">{faq.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="max-w-3xl mx-auto px-6 pb-24 text-center space-y-6">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-white leading-[1.12]">{t('pricing.bottomCtaTitle')}</h2>
          <p className="text-base max-w-xl mx-auto leading-relaxed text-white/60">{t('pricing.bottomCtaSubtitle')}</p>
          <Button
            size="lg"
            className="h-12 px-8 text-sm font-bold rounded-xl text-white border-0"
            style={{ background: '#5b5fef' }}
            onClick={() => navigate('/register')}
          >
            {t('cta.button')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </section>

        {/* Footer */}
        <footer className="py-10 border-t border-white/[0.06]">
          <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <img src="/Unimind_logo.png" alt="UniMind" className="h-7 w-7 rounded-lg object-contain" />
              <span className="font-bold text-sm tracking-tight text-white/70">UniMind.ai</span>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-white/40">
              <Link to="/privacy" className="hover:text-white/70 transition-colors">隐私政策</Link>
              <Link to="/terms" className="hover:text-white/70 transition-colors">用户协议</Link>
              <span>© {COPYRIGHT_YEAR} {COPYRIGHT_ENTITY} · {APP_VERSION}</span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default PricingPage;
