import { useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowsClockwise } from '@phosphor-icons/react';
import { t } from '@/i18n';
import type { FlashcardMastery, SourceAnchor, StudioFlashcard, WorkbenchCitation } from '@/types/workbench';
import { CitationPill } from './CitationPill';
import { flashcardStep } from './studioPractice';

type Rating = Exclude<FlashcardMastery, 'unseen'>;

export function FlashcardDeckView({ cards, citations, conversationId, onSelect, onRate, saving }: {
  cards: StudioFlashcard[];
  citations: WorkbenchCitation[];
  conversationId: string;
  onSelect: (anchor: SourceAnchor) => void;
  onRate: (cardId: string, rating: Rating) => void;
  saving: boolean;
}) {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const flipButton = useRef<HTMLButtonElement>(null);
  const card = cards[index];
  const citation = citations.find(row => row.cite_key === card.cite_key);
  const mastered = cards.filter(row => row.mastery === 'mastered').length;
  const move = (key: string) => {
    const next = flashcardStep(index, key, cards.length);
    if (next !== index) {
      setFlipped(false);
      setIndex(next);
    }
  };

  return <section className="um-wb-deck" aria-label={t('闪卡组')} onKeyDown={event => {
    if (event.altKey || event.ctrlKey || event.metaKey || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    move(event.key);
  }}>
    <div className="um-wb-deck-counts" aria-live="polite">
      <span>{t('第 {0} 张，共 {1} 张', { 0: index + 1, 1: cards.length })}</span>
      <span>{t('已掌握 {0} 张', { 0: mastered })}</span>
    </div>
    <progress className="um-wb-studio-progress" value={index + 1} max={cards.length} aria-label={t('闪卡进度')} />
    <div className="um-wb-flashcard" data-flipped={flipped}>
      <button type="button" className="um-wb-card-face um-wb-card-front" aria-label={`${card.front} · ${t('查看答案')}`}
        aria-hidden={flipped || undefined} inert={flipped} onClick={() => { setFlipped(true); flipButton.current?.focus(); }}>
        <small>{t('正面 · 问题')}</small>
        <strong>{card.front}</strong>
        {card.hint && <span>{t('提示：{0}', { 0: card.hint })}</span>}
      </button>
      <div className="um-wb-card-face um-wb-card-back" aria-hidden={!flipped || undefined} inert={!flipped}>
        <small>{t('背面 · 答案')}</small>
        <p>{card.back}</p>
        {citation && <CitationPill citation={citation} conversationId={conversationId} onSelect={onSelect} />}
      </div>
    </div>
    <div className="um-wb-studio-tools">
      <button type="button" className="um-agent-button" ref={flipButton} aria-pressed={flipped} onClick={() => setFlipped(!flipped)}>
        <ArrowsClockwise size={15} />{flipped ? t('查看问题') : t('查看答案')}
      </button>
      <button type="button" className="um-agent-button" disabled={saving || !flipped} aria-pressed={card.mastery === 'learning'}
        onClick={() => onRate(card.id, 'learning')}>{t('待加强')}</button>
      <button type="button" className="um-agent-button" disabled={saving || !flipped} aria-pressed={card.mastery === 'mastered'}
        onClick={() => onRate(card.id, 'mastered')}>{t('已掌握')}</button>
    </div>
    <div className="um-wb-deck-controls">
      <button type="button" className="um-agent-button" disabled={index === 0} onClick={() => move('ArrowLeft')}><ArrowLeft size={15} />{t('上一张')}</button>
      <button type="button" className="um-agent-button" disabled={index === cards.length - 1} onClick={() => move('ArrowRight')}>{t('下一张')}<ArrowRight size={15} /></button>
    </div>
  </section>;
}
