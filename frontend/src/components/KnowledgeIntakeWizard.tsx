import { useState } from 'react';
import { inquireKnowledgeRequirements } from '@/lib/knowledgeBuilderApi';
import type { BuildArchetype, IntakeMode, IntakeRequestPayload, IntakeResponsePayload, RequirementsDraft } from '@/types/knowledgeBuilder';
import { Button } from '@/components/ui/button';

interface Props {
  subject: string;
  archetype: BuildArchetype;
  building: boolean;
  onBuild: (requirements?: RequirementsDraft) => void;
}

const archetypeLabels: Record<BuildArchetype, string> = {
  auto: '自动识别', institution_mechanism_theory: '制度 · 机制 · 理论辨析', formula_derivation_chain: '公式 · 推导 · 定量演绎',
  taskflow_diagnostic_tree: '流程 · 排障 · 实务作业', case_synthesis_deduction: '案例 · 要件 · 综合推演',
};

export function KnowledgeIntakeWizard({ subject, archetype, building, onBuild }: Props) {
  const [mode, setMode] = useState<IntakeMode>('card');
  const [response, setResponse] = useState<IntakeResponsePayload | null>(null);
  const [cardAnswers, setCardAnswers] = useState<NonNullable<IntakeRequestPayload['card_answers']>>({});
  const [messages, setMessages] = useState<NonNullable<IntakeRequestPayload['messages']>>([]);
  const [chatInput, setChatInput] = useState('');
  const [selfReport, setSelfReport] = useState('');
  const [diagnosticAnswers, setDiagnosticAnswers] = useState<Record<string, string>>({});
  const [showDiagnostic, setShowDiagnostic] = useState(false);
  const [pending, setPending] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');

  const request = async (chat = false) => {
    if (!subject.trim() || pending) return;
    const nextMessages = chat && chatInput.trim() ? [...messages, { role: 'user' as const, content: chatInput.trim() }] : messages;
    setPending(true); setError('');
    try {
      const result = await inquireKnowledgeRequirements({ subject: subject.trim(), mode, messages: nextMessages,
        card_answers: cardAnswers, self_report: selfReport,
        ...(response ? { diagnostic_questions: response.diagnostic_questions, diagnostic_answers: diagnosticAnswers } : {}),
      });
      setResponse(previous => previous ? { ...result, cards: previous.cards } : result); setDirty(false);
      if (chat) { setMessages([...nextMessages, { role: 'assistant', content: result.assistant_reply }]); setChatInput(''); }
    } catch { setError('需求引导暂时未完成，请检查网络和内容访问配置后重试。'); }
    finally { setPending(false); }
  };
  const changeCard = (dimension: string, selected?: string[], custom?: string) => {
    const current = cardAnswers[dimension] ?? { selected: [], custom: '' };
    setCardAnswers({ ...cardAnswers, [dimension]: { selected: selected ?? current.selected, custom: custom ?? current.custom } });
    setDirty(true);
  };
  const draft = response?.requirements_draft;
  const baseline = draft?.baseline_summary;
  const busy = pending || building;

  return <section className="kb-intake" aria-label="构建前需求引导">
    <div role="tablist" aria-label="需求引导模式" className="kb-intake-tabs">
      <button type="button" role="tab" aria-selected={mode === 'card'} onClick={() => setMode('card')}>卡片模式（推荐）</button>
      <button type="button" role="tab" aria-selected={mode === 'chat'} onClick={() => setMode('chat')}>详细对话模式</button>
    </div>
    {response?.catalog_match.matched_subject && <div className="kb-intake-catalog" role="status">
      已匹配「{response.catalog_match.matched_subject}」：{response.catalog_match.module_count} 个既有章节 · {response.catalog_match.kp_count} 个知识点 · {response.catalog_match.edge_count} 条关系。
      已有 {response.catalog_match.assessed_kp_count} 个掌握度记录，平均掌握度 {Math.round(response.catalog_match.avg_mastery * 100)}%。
    </div>}
    {mode === 'card' ? <div role="tabpanel" aria-label="卡片问答">
      {!response ? <Button type="button" disabled={busy || !subject.trim()} onClick={() => void request()}>生成需求卡片</Button> : <div className="kb-intake-cards">
        {response.cards.map(card => <fieldset key={card.id} className="kb-intake-card" disabled={busy}>
          <legend>{card.title}</legend><p>{card.question}</p>
          <div className="kb-intake-options">{card.options.map(option => {
            const selected = cardAnswers[card.dimension]?.selected ?? [];
            return <button type="button" key={option.value} aria-pressed={selected.includes(option.value)} title={option.description}
              onClick={() => changeCard(card.dimension, card.multi_select
                ? selected.includes(option.value) ? selected.filter(v => v !== option.value) : [...selected, option.value]
                : [option.value])}>{option.label}<small>{option.description}</small></button>;
          })}</div>
          {card.allow_custom && <label>补充要求<textarea value={cardAnswers[card.dimension]?.custom ?? ''}
            onChange={e => changeCard(card.dimension, undefined, e.target.value)} placeholder="可填写教材版本、考纲、排除范围等" /></label>}
        </fieldset>)}
      </div>}
    </div> : <div role="tabpanel" aria-label="详细需求对话" className="kb-intake-chat">
      <div className="kb-intake-messages" aria-live="polite">{messages.length === 0 && <p>可以粘贴考纲、说明教材版本，或从学习目标和薄弱章节开始。</p>}
        {messages.map((message, i) => <p key={i} data-role={message.role}><strong>{message.role === 'user' ? '我' : '需求助手'}：</strong>{message.content}</p>)}
      </div>
      <label>补充你的学习需求<textarea value={chatInput} disabled={busy} onChange={e => setChatInput(e.target.value)} placeholder="例如：准备 431，重点公司理财，需要逐步推导；学过货币银行学，但 CAPM 不熟。" /></label>
      <Button type="button" disabled={busy || !subject.trim() || !chatInput.trim()} onClick={() => void request(true)}>发送并提炼需求</Button>
    </div>}
    {response && <>
      <button type="button" className="kb-intake-link" onClick={() => setShowDiagnostic(v => !v)}>{showDiagnostic ? '收起基础摸底' : '测一测我的基础'}</button>
      {(response.needs_diagnostic || showDiagnostic || !!baseline?.answered_count) && <section className="kb-intake-diagnostic" aria-label="基础摸底">
        <h3>基础摸底（自述 + 快测）</h3>
        <label>我已经懂了哪些 / 哪些还不熟<textarea value={selfReport} disabled={busy}
          onChange={e => { setSelfReport(e.target.value); setDirty(true); }} placeholder="学过货币银行学基础，但对 WACC 和 CAPM 计算不熟。" /></label>
        <p>系统保留完整前置依赖图，根据摸底结果标记推荐起点块 ENTRY，并调整核心、拓展内容与讲解深度。</p>
        {response.diagnostic_questions.map((q, i) => {
          const result = !dirty ? baseline?.results.find(r => r.id === q.id) : undefined;
          return <fieldset key={q.id} className="kb-intake-card" disabled={busy}>
            <legend>{i + 1}. {q.topic} · {q.source === 'question_bank' ? '题库' : '基础探测'}</legend><p>{q.stem}</p>
            <div className="kb-intake-options">{q.options.map(o => <button type="button" key={o.key} aria-pressed={diagnosticAnswers[q.id] === o.key}
              onClick={() => { setDiagnosticAnswers({ ...diagnosticAnswers, [q.id]: o.key }); setDirty(true); }}>{o.key} · {o.label}</button>)}</div>
            {result && <p role="status">{result.correct ? '回答正确' : `需要强化，正确答案：${result.correct_answer}`}。{result.explanation}</p>}
          </fieldset>;
        })}
        <Button type="button" disabled={busy || Object.keys(diagnosticAnswers).length === 0} onClick={() => void request()}>提交快测并更新基础评估</Button>
        {!!baseline?.answered_count && !dirty && <p role="status">已答 {baseline.answered_count} 题，答对 {baseline.correct_count} 题，正确率 {Math.round(baseline.accuracy * 100)}%。{baseline.entry_strategy}</p>}
      </section>}
      <section className="kb-intake-summary" aria-label="构建需求确认单" aria-live="polite">
        <h3>构建需求确认单</h3>
        {dirty && <p>有新的回答，请更新确认单后构建。</p>}
        {draft && <dl>
          <dt>学习目的</dt><dd>{draft.learning_goal || '待补充'}</dd>
          <dt>重点模块</dt><dd>{draft.scope_inclusions.join('、') || '待补充'}</dd>
          <dt>暂不展开</dt><dd>{draft.scope_exclusions.join('、') || '未指定'}</dd>
          <dt>推导深度</dt><dd>{draft.depth_preference || '待补充'}</dd>
          <dt>已有基础</dt><dd>{draft.learner_background || '待了解'}</dd>
          <dt>基础起点策略</dt><dd>{draft.baseline_summary.entry_strategy}</dd>
          <dt>推荐入口主题</dt><dd>{draft.suggested_entry_topics.join('、') || '基础概念与核心机制'}</dd>
          <dt>结构范式</dt><dd>{archetypeLabels[archetype === 'auto' ? draft.recommended_archetype : archetype]}</dd>
        </dl>}
        {mode === 'card' && <p>{response.assistant_reply}</p>}
        <Button type="button" variant="outline" disabled={busy} onClick={() => void request()}>更新需求确认单</Button>
        <Button type="button" disabled={busy || dirty || !response.ready_to_build} onClick={() => draft && onBuild(draft)}>按此需求构建知识树</Button>
      </section>
    </>}
    {pending && <p role="status">正在整理需求与摸底题目…</p>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
    <Button type="button" variant="ghost" disabled={busy || !subject.trim()} onClick={() => onBuild()}>跳过问答，直接默认构建</Button>
  </section>;
}
