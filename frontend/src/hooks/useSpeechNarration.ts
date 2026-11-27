import { useCallback, useEffect, useRef, useState } from 'react';

function stripForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\$\$[\s\S]*?\$\$/g, ' 公式 ')
    .replace(/\$[^$]+\$/g, ' 公式 ')
    .replace(/[#>*_`~]/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

export function useSpeechNarration() {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  const [speakingKey, setSpeakingKey] = useState<string | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setSpeakingKey(null);
  }, [supported]);

  const toggleSpeak = useCallback((key: string, text: string) => {
    if (!supported) return;
    if (speakingKey === key) {
      stop();
      return;
    }
    const clean = stripForSpeech(text);
    if (!clean) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.04;
    const voices = window.speechSynthesis.getVoices?.() ?? [];
    const zhVoice = voices.find(v => /zh[-_]CN/i.test(v.lang)) ?? voices.find(v => /^zh/i.test(v.lang));
    if (zhVoice) utterance.voice = zhVoice;
    utterance.onend = () => {
      utteranceRef.current = null;
      setSpeakingKey(prev => (prev === key ? null : prev));
    };
    utterance.onerror = () => {
      utteranceRef.current = null;
      setSpeakingKey(prev => (prev === key ? null : prev));
    };
    utteranceRef.current = utterance;
    setSpeakingKey(key);
    window.speechSynthesis.speak(utterance);
  }, [speakingKey, stop, supported]);

  useEffect(() => () => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);

  return { supported, speakingKey, toggleSpeak, stop };
}
