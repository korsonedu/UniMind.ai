import { useState, useEffect, useRef } from 'react';

interface UseTypewriterOptions {
  words: string[];
  typingSpeed?: number;
  deletingSpeed?: number;
  pauseDuration?: number;
}

export function useTypewriter({
  words,
  typingSpeed = 80,
  deletingSpeed = 40,
  pauseDuration = 2000,
}: UseTypewriterOptions) {
  const [text, setText] = useState('');
  const wordIndexRef = useRef(0);
  const isDeletingRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (words.length === 0) return;

    const tick = () => {
      const currentWord = words[wordIndexRef.current];

      if (!isDeletingRef.current) {
        // Typing: add one character
        const nextLen = text.length + 1;
        setText(currentWord.slice(0, nextLen));

        if (nextLen >= currentWord.length) {
          // Pause, then start deleting
          timeoutRef.current = setTimeout(() => {
            isDeletingRef.current = true;
            tick();
          }, pauseDuration);
          return;
        }
        timeoutRef.current = setTimeout(tick, typingSpeed);
      } else {
        // Deleting: remove one character
        const nextLen = text.length - 1;
        setText(currentWord.slice(0, Math.max(0, nextLen)));

        if (nextLen <= 0) {
          // Move to next word
          isDeletingRef.current = false;
          wordIndexRef.current = (wordIndexRef.current + 1) % words.length;
          timeoutRef.current = setTimeout(tick, typingSpeed);
          return;
        }
        timeoutRef.current = setTimeout(tick, deletingSpeed);
      }
    };

    timeoutRef.current = setTimeout(tick, pauseDuration);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  // Re-run when text changes to advance character by character
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, words, typingSpeed, deletingSpeed, pauseDuration]);

  return text;
}
