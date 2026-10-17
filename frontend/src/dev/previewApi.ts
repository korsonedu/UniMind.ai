import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { FEATURES } from '@/store/useInstitutionStore';
import { AxiosError } from 'axios';
import type { DashData } from '@/pages/course-center/LearningOverview';
import type { Message } from '@/hooks/useAgentConversation';
import './previewSocket';

if (!import.meta.env.DEV) throw new Error('Development fixtures only.');

// Local fixtures only. Never persist a preview identity or call a production API.
useAuthStore.persist.setOptions({ storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } });
useAuthStore.setState({ user: { id: 0, username: 'preview', nickname: '宇驰', role: 'student', elo_score: 1280, avatar_url: '', avatar_style: '', avatar_seed: '', bio: '', allow_broadcast: false, show_others_broadcast: false, is_member: true, has_completed_initial_assessment: true, institution_id: 0, institution_role: 'student', institution: { id: 0, name: 'UniMind.ai', slug: 'preview', plan: 'growth', plan_label: 'Growth', is_plan_active: true, max_students: 100, student_count: 1, invite_slug: '' }, tour_dismissed_at: new Date().toISOString(), tour_panel_dismissed_at: new Date().toISOString() }, token: null });
const date = (offset = 0) => { const value = new Date(); value.setDate(value.getDate() + offset); return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(value); };
const memorySeries = [.67, .72, .74, .7, .78, .82, .81, .84].map((predicted, index) => ({ date: date(-28 + index * 4), predicted, actual: [.6, .7, .8, .7, .9, .9, .8, 1][index], count: 10 }));
const role = sessionStorage.getItem('unimind-preview-role') || 'student';
const blockedFeatures = new URLSearchParams(location.search).getAll('blocked');
const lessonDemo = new URLSearchParams(location.search).has('lessonDemo');
const user = { ...useAuthStore.getState().user!, id: 1, institution_id: 1, institution: { ...useAuthStore.getState().user!.institution!, id: 1 },
  role: (role === 'admin' ? 'admin' : 'student') as 'student' | 'admin', institution_role: role === 'teacher' ? 'owner' : 'student',
  is_admin: role === 'admin', is_institution_admin: role === 'teacher', is_institution_owner: role === 'teacher', is_institution_teacher: role === 'teacher' };
useAuthStore.setState({ user });
const kps = [{ id: 1, name: '金融学', description: '金融市场与货币政策', parent: null, level: 0, order: 0, questions_count: 24 }, { id: 2, name: '货币政策', description: '利率与货币政策传导', parent: 1, level: 1, order: 0, questions_count: 12 }];
const practiceQuestions = [
  { id: 101, text: '央行降低政策利率，通常会通过哪条路径影响实体经济？', q_type: 'objective', options: ['融资成本下降，消费与投资增加', '融资成本上升，消费与投资减少', '货币需求完全不变', '所有资产价格保持不变'], difficulty_level: 'normal', difficulty_level_display: '适当', difficulty: 1200, knowledge_point: 2, knowledge_point_detail: kps[1], is_favorite: false, is_mastered: false },
  { id: 102, text: '未来两年后收到 100 元，年利率为 5%。现值的计算式是？\n\n$$PV = \\frac{FV}{(1+r)^n}$$', q_type: 'objective', options: ['$100 / (1.05)^2$', '$100 \\times (1.05)^2$', '$100 / 1.10$', '$100 \\times 1.10$'], difficulty_level: 'hard', difficulty_level_display: '困难', difficulty: 1400, knowledge_point: 2, knowledge_point_detail: kps[1], is_favorite: false, is_mastered: false },
  { id: 103, text: '解释政策利率如何通过融资成本影响消费与投资，并说明一种可能阻碍传导的因素。', q_type: 'subjective', subjective_type: 'short', options: null, difficulty_level: 'hard', difficulty_level_display: '困难', difficulty: 1400, knowledge_point: 2, knowledge_point_detail: kps[1], is_favorite: false, is_mastered: false },
];
const albums = [{ id: 1, name: '金融学基础' }];
const courses = ['金融市场与利率', '货币政策的传导', '风险与收益'].map((title, index) => ({ id: index + 1, title, description: '本地示例课程', subject_name: '金融学', module: index < 2 ? 1 : 2, module_name: index < 2 ? '货币与金融市场' : '风险管理', module_sort_order: index < 2 ? 0 : 1, album: albums[0], tags: ['金融学', '基础'], knowledge_points: [2], video_file: '/local-preview-video.mp4', cover_image: '', created_at: date(-7), knowledge_point: 2, video_url: '', thumbnail: '', duration: 1200 + index * 180, elo_reward: 20, sort_order: index, materials: [], progress: index === 0 ? { last_position: 380, is_finished: false, updated_at: date(-1) } : index === 1 ? { last_position: 1380, is_finished: true, updated_at: date(-2) } : null }));
const achievements = [{ id: 1, key: 'diagnostic', name: '首次诊断', description: '完成首次学习诊断', icon: '🎯', category: 'diagnostic', category_label: '首次诊断', threshold: 1, is_unlocked: true, unlocked_at: date(-7), progress: 1 }, { id: 2, key: 'streak7', name: '连续学习 7 天', description: '连续学习七天解锁', icon: '📅', category: 'streak', category_label: '连续打卡', threshold: 7, is_unlocked: false, unlocked_at: null, progress: 6 }];
const articles = [{ id: 1, title: '理解货币政策的传导', content: '<p>从政策利率、融资成本与消费投资三个环节理解货币政策。</p>', summary: '政策利率如何影响经济活动', tags: ['金融学'], author_display_name: 'UniMind', created_at: date(-2), updated_at: date(-1), view_count: 36 }];
const plans: { id: number; content: string; is_completed: boolean }[] = [{ id: 1, content: '复习货币政策', is_completed: false }];
const messages: { id: number; content: string; timestamp: string; user_detail: typeof user }[] = [];
const qaTeacher = { ...user, id: 2, username: 'teacher-preview', nickname: '陈老师' };
const qaAnswers = [
  { id: 701, question: 601, content: '先区分政策利率和市场利率。政策利率影响银行的资金成本，再通过信贷、资产价格和预期影响消费与投资。\n\n传导需要时间，也会受到银行放贷意愿与企业投资预期的影响。', is_teacher: true, created_at: `${date()}T02:20:00Z`, user_detail: qaTeacher, likes_count: 3, is_liked: false },
  { id: 702, question: 601, content: '明白了，如果企业对未来收益预期较弱，即使融资成本降低，也可能不增加投资，对吗？', is_teacher: false, created_at: `${date()}T02:30:00Z`, user_detail: user, likes_count: 0, is_liked: false },
  { id: 703, question: 601, content: '对，这就是预期影响传导效果的一个例子。回答时可以把融资成本和预期分别解释，再说明两者如何共同影响投资决策。', is_teacher: true, created_at: `${date()}T02:40:00Z`, user_detail: qaTeacher, likes_count: 1, is_liked: false },
];
const qaQuestions: Array<{
  id: number; content: string; attachment: string | null; is_solved: boolean; is_starred: boolean;
  created_at: string; user_detail: typeof user; answers: typeof qaAnswers;
  first_answer: (typeof qaAnswers)[number] | null; reply_count: number;
  likes_count: number; is_liked: boolean; is_followed: boolean;
}> = [
  { id: 601, content: '政策利率下降后，为什么消费和投资不一定马上增加？\n\n我理解融资成本会降低，但不太清楚银行信贷和市场预期在这里分别起什么作用。', attachment: null, is_solved: true, is_starred: true, created_at: `${date()}T02:00:00Z`, user_detail: user, answers: qaAnswers, first_answer: qaAnswers[0], reply_count: 3, likes_count: 5, is_liked: false, is_followed: false },
  { id: 602, content: '如何理解现值计算中的折现率？\n\n我在比较两笔未来现金流时有些困惑。未来两年后收到的金额相同，但其中一笔来自国债，另一笔来自企业债券。\n\n如果直接使用相同的折现率，计算出来的现值也会一样。但企业债券的违约风险更高，我感觉这个风险应该在计算中有所体现。\n\n我的问题是：折现率应该只考虑资金的时间价值，还是同时考虑风险补偿？选择折现率时，应该先确定一个无风险利率，再加入风险溢价吗？\n\n另外，如果市场利率变化，已经发行的固定利率债券价格也会变化。这个变化能否直接从现值公式中解释？\n\n希望老师能结合一个简单例子，把现金流、折现率和债券价格之间的关系串起来。', attachment: null, is_solved: false, is_starred: false, created_at: `${date()}T01:00:00Z`, user_detail: { ...user, id: 3, username: 'classmate-preview', nickname: '林同学' }, answers: [], first_answer: null, reply_count: 0, likes_count: 0, is_liked: false, is_followed: false },
];
const watchLater: { course: number; created_at: string }[] = [{ course: 3, created_at: date() }];
const courseActivity = Array.from({ length: 28 }, (_, i) => ({ date: date(i - 27), course: i % 2 + 1, watched_seconds: i % 5 ? (i * 211) % 2300 : 0, completions: i === 26 ? 1 : 0, elo_earned: i === 26 ? 20 : 0 }));
let learningGoal: { title: string; deadline: string; courses: number[] } | null = JSON.parse(sessionStorage.getItem('unimind-preview-goal') || 'null');
const dashboard: DashData = {
  stats: { streak_days: 6, weekly_activity: 42, accuracy: 82, total_attempted: 236, attempted_questions: 180, total_attempts: 236, last_accuracy: 82, lifetime_accuracy: 79.5, has_attempts: true, is_new_user: new URLSearchParams(location.search).has('new'), today_checked_in: false, checkin_streak: 5, checkin_history: [], unlocked_achievement_count: 3,
    heatmap_days: Array.from({ length: 28 }, (_, i) => ({ date: date(i - 27), count: i % 5 === 0 ? 0 : (i * 7) % 20 })),
    next_achievements: [{ key: 'streak7', name: '连续学习 7 天', description: '连续学习七天解锁。', icon: '', category: 'streak' }, { key: 'practice300', name: '完成 300 道练习', description: '累计完成三百道练习解锁。', icon: '', category: 'practice' }],
  }, reviews: { due_count: 8 }, exams: [{ id: 1, total_score: 82, max_score: 100, percentage: 82, elo_change: 24, created_at: date(-1) }],
};
let history: Message[] = [
  { id: 1, role: 'user', content: '帮我理解货币政策的传导过程', timestamp: `${date(-1)}T08:00:00Z`, conversation_id: 'sample-finance', conversation_title: '货币政策与利率' },
  { id: 2, role: 'assistant', content: '可以从三个环节理解：政策利率、市场融资成本、消费与投资。\n\n利率变化会影响资金需求，但传导速度还取决于银行信贷和市场预期。', timestamp: `${date(-1)}T08:01:00Z`, conversation_id: 'sample-finance', conversation_title: '货币政策与利率' },
  { id: 3, role: 'user', content: '安排今天的复习', timestamp: `${date()}T08:00:00Z`, conversation_id: 'sample-review', conversation_title: '今天的复习安排' },
  { id: 4, role: 'assistant', content: '先复习利率与货币政策，再完成 8 道到期题目。\n\n复习后可以再用一道题检查理解。\n\n$$PV = \\frac{FV}{(1+r)^n}$$', timestamp: `${date()}T08:01:00Z`, conversation_id: 'sample-review', conversation_title: '今天的复习安排' },
];
const projectFixtures: { projects: { id: number; name: string; instructions: string }[]; assignments: Record<string, number | null> } = JSON.parse(sessionStorage.getItem('unimind-preview-projects') || '{"projects":[],"assignments":{}}');
const saveProjects = () => sessionStorage.setItem('unimind-preview-projects', JSON.stringify(projectFixtures));
history = history.map(message => ({ ...message, conversation_project: projectFixtures.assignments[message.conversation_id!] ?? null }));
api.defaults.adapter = async config => {
  let data: unknown = {};
  const payload = typeof config.data === 'string' ? JSON.parse(config.data || '{}') : config.data;
  const url = new URL(config.url || '', location.origin);
  const path = url.pathname;
  const params = new URLSearchParams(url.search);
  Object.entries(config.params || {}).forEach(([key, value]) => params.set(key, String(value)));
  switch (path) {
    case '/users/me/': data = user; break;
    case '/ai/bots/': data = [{ id: 1, name: '小宇', bot_type: 'planner', avatar: null }, { id: 2, name: '出题助手', bot_type: 'exam_generator', avatar: null }]; break;
    case '/ai/history/': data = history; break;
    case '/ai/projects/': if (config.method === 'post') { const project = { id: Date.now(), name: payload.name, instructions: payload.instructions || '' }; projectFixtures.projects.push(project); saveProjects(); data = project; } else data = projectFixtures.projects; break;
    case '/ai/dashboard/': data = dashboard; break;
    case '/users/me/checkin/': data = { created: !dashboard.stats.today_checked_in }; if (!dashboard.stats.today_checked_in) dashboard.stats.checkin_streak++; dashboard.stats.today_checked_in = true; break;
    case '/ai/delete-conversation/': history = history.filter(message => message.conversation_id !== payload.conversation_id); delete projectFixtures.assignments[payload.conversation_id]; saveProjects(); break;
    case '/ai/reset/': break;
    case '/ai/feedback/': history = history.map(message => message.id === payload.message_id ? { ...message, feedback: payload.feedback } : message); break;
    case '/users/institution/me/features/': data = { features: Object.values(FEATURES).filter(feature => !blockedFeatures.includes(feature)), is_platform_admin: false, institution: user.institution, usage: null }; break;
    case '/notifications/unread-count/': data = { unread_count: 0, count: 0 }; break;
    case '/notifications/': data = []; break;
    case '/users/achievements/': data = achievements; break;
    case '/users/me/achievements/': data = achievements.filter(item => item.is_unlocked); break;
    case '/users/nps/status/': data = { should_show: false }; break;
    case '/users/institution/me/students/ranking/': data = [user]; break;
    case '/courses/tags/': data = [{ name: '金融学', count: 3 }, { name: '基础', count: 3 }]; break;
    case '/courses/learning-progress/': data = courses.filter(c => c.progress).map(c => ({ course: c.id, ...c.progress, duration: c.duration })); break;
    case '/courses/learning-goal/': {
      if (config.method === 'put') { learningGoal = { title: payload.title, deadline: payload.deadline, courses: payload.courses }; sessionStorage.setItem('unimind-preview-goal', JSON.stringify(learningGoal)); }
      const completed = courses.filter(course => learningGoal?.courses.includes(course.id) && course.progress?.is_finished).length;
      data = learningGoal ? { ...learningGoal, total_courses: learningGoal.courses.length, completed_courses: completed, progress_percent: learningGoal.courses.length ? Math.round(completed / learningGoal.courses.length * 100) : 0 } : null; break;
    }
    case '/courses/learning-activity/': data = { today: date(), tracking_started_at: date(-28), days: courseActivity, totals: [1, 2].map(course => ({ course, watched_seconds: courseActivity.filter(item => item.course === course).reduce((sum, item) => sum + item.watched_seconds, 0), completions: course === 1 ? 1 : 0, elo_earned: course === 1 ? 20 : 0 })) }; break;
    case '/courses/watch-later/': data = watchLater; break;
    case '/courses/albums/': data = albums; break;
    case '/courses/': {
      const filtered = courses.filter(course => !params.get('search') || course.title.includes(params.get('search')!));
      data = params.has('page_size') ? { items: filtered, total_pages: 1, count: filtered.length } : filtered; break;
    }
    case '/quizzes/knowledge-points/': data = kps; break;
    case '/users/me/knowledge-mastery/': data = { '1': 'learning', '2': 'learning' }; break;
    case '/users/me/report-card/': data = { student: { ...user, date_joined: date(-60) }, stats: { total_attempted: 236, total_distinct: 180, correct_count: 148, wrong_count: 42, mastered_count: 128, accuracy: 82.2, study_streak: 6, checkin_streak: 5 }, radar: [{ subject: '金融学', avg_mastery: 72, kp_count: 12 }, { subject: '经济学', avg_mastery: 65, kp_count: 8 }, { subject: '数学', avg_mastery: 84, kp_count: 10 }], daily_activity: dashboard.stats.heatmap_days, exams: dashboard.exams, achievements: achievements.filter(a => a.is_unlocked) }; break;
    case '/articles/': data = { articles, tag_stats: [{ tag: '金融学', count: 1 }], total_pages: 1 }; break;
    case '/qa/questions/': {
      if (config.method === 'post') {
        const question = { id: Date.now(), content: String((config.data as FormData).get('content')), attachment: null, is_solved: false, is_starred: false, created_at: new Date().toISOString(), user_detail: user, answers: [], first_answer: null, reply_count: 0, likes_count: 0, is_liked: false, is_followed: false };
        qaQuestions.unshift(question); data = question;
      } else data = qaQuestions.filter(q => (!params.get('search') || `${q.content}${q.user_detail.nickname}`.includes(params.get('search')!)) && (params.get('filter') === 'solved' ? q.is_solved : params.get('filter') === 'unsolved' ? !q.is_solved : params.get('filter') === 'followed' ? q.is_followed : params.get('filter') === 'starred' ? q.is_starred : true));
      break;
    }
    case '/qa/answers/': {
      const question = qaQuestions.find(q => q.id === payload.question)!;
      const isTeacher = role === 'teacher' || role === 'admin';
      if (!question.answers.length && !isTeacher) throw new AxiosError('首个回答必须由教师完成', 'PREVIEW_FORBIDDEN', config);
      const answer = { id: Date.now(), question: question.id, content: payload.content, is_teacher: isTeacher, created_at: new Date().toISOString(), user_detail: user, likes_count: 0, is_liked: false };
      question.answers.push(answer); question.reply_count = question.answers.length;
      if (!question.first_answer) { question.first_answer = answer; question.is_solved = true; }
      data = answer; break;
    }
    case '/users/online/': data = [user]; break;
    case '/study/messages/': if (config.method === 'post') messages.push({ id: Date.now(), content: payload.content, timestamp: new Date().toISOString(), user_detail: user }); data = messages; break;
    case '/users/plans/': if (config.method === 'post') { const plan = { id: Date.now(), content: payload.content, is_completed: false }; plans.push(plan); data = plan; } else data = plans; break;
    case '/quizzes/stats/': data = { review_goal: 8, new_questions: 10, at_risk_count: 3, recommended_questions: 18, estimated_minutes: 20, weak_focus_count: 2 }; break;
    case '/quizzes/questions/': {
      const ids = params.get('ids')?.split(',').map(Number);
      let questions = ids ? ids.flatMap(id => practiceQuestions.filter(question => question.id === id)) : practiceQuestions;
      if (params.get('difficulty_level')) questions = questions.filter(question => question.difficulty_level === params.get('difficulty_level'));
      if (params.get('sub_ids') && !params.get('sub_ids')!.split(',').some(id => ['1', '2'].includes(id))) questions = [];
      data = questions.slice(0, Number(params.get('limit') || questions.length)); break;
    }
    case '/quizzes/favorite/toggle/': { const question = practiceQuestions.find(question => question.id === payload.question_id)!; question.is_favorite = !question.is_favorite; data = { is_favorite: question.is_favorite }; break; }
    case '/quizzes/mastered/toggle/': { const question = practiceQuestions.find(question => question.id === payload.question_id)!; question.is_mastered = !question.is_mastered; data = { is_mastered: question.is_mastered }; break; }
    case '/quizzes/submit-exam/': data = { status: 'queued' }; break;
    case '/quizzes/memorix/curve/': data = { window_days: 90, time_series: memorySeries, fit_curve: [], metrics: { review_count: 80, rmse: null, mae: null, avg_predicted: .76, avg_actual: .8 }, profile: { last_optimized_at: `${date(-1)}T08:00:00Z`, current_loss: null, total_reviews_used: 80 } }; break;
    case '/quizzes/memorix/optimization-history/': data = { results: [{ id: 1, improvement_ratio: .045, reviews_used: 60, accepted: true, created_at: `${date(-1)}T08:00:00Z` }] }; break;
    case '/quizzes/wrong-questions/insights/': data = { overview: { wrong_questions: 2, wrong_attempts: 5 }, recommended_drills: [{ drill_type: 'cause', drill_key: 'concept', drill_label: '概念理解', question_count: 2, question_ids: [103, 101], recommended_questions: 2 }, { drill_type: 'knowledge_point', drill_key: '2', drill_label: '货币政策', question_count: 2, question_ids: [103, 101], recommended_questions: 2 }], cause_breakdown: [{ cause_key: 'concept', cause_label: '概念理解', question_count: 2, wrong_attempts: 5, ratio: 1 }], knowledge_point_breakdown: [{ knowledge_point_id: 2, knowledge_point_name: '货币政策', question_count: 2, avg_wrong_count: 2.5 }] }; break;
    case '/payments/orders/': data = []; break;
    default:
      if (/^\/qa\/questions\/\d+\/$/.test(path)) {
        const index = qaQuestions.findIndex(q => q.id === Number(path.split('/')[3]));
        if (index < 0) throw new AxiosError('问题不存在', 'PREVIEW_NOT_FOUND', config);
        const question = qaQuestions[index];
        if (config.method === 'delete') qaQuestions.splice(index, 1);
        else {
          if (config.method === 'patch') question.content = payload.content;
          data = question;
        }
      }
      else if (/^\/qa\/questions\/\d+\/action\/$/.test(path)) {
        const question = qaQuestions.find(q => q.id === Number(path.split('/')[3]))!;
        if (payload.toggle_follow) question.is_followed = !question.is_followed;
        if (payload.toggle_like) { question.is_liked = !question.is_liked; question.likes_count += question.is_liked ? 1 : -1; }
        if (payload.toggle_star) question.is_starred = !question.is_starred;
        if (payload.toggle_solved) question.is_solved = !question.is_solved;
        data = question;
      }
      else if (/^\/qa\/answers\/\d+\/action\/$/.test(path)) {
        const answer = qaQuestions.flatMap(q => q.answers).find(a => a.id === Number(path.split('/')[3]))!;
        answer.is_liked = !answer.is_liked; answer.likes_count += answer.is_liked ? 1 : -1; data = answer;
      }
      else if (/^\/ai\/projects\/\d+\/$/.test(path)) {
        const id = Number(path.split('/')[3]);
        if (config.method === 'delete') { projectFixtures.projects = projectFixtures.projects.filter(project => project.id !== id); history = history.filter(message => message.conversation_project !== id); Object.entries(projectFixtures.assignments).forEach(([key, value]) => { if (value === id) delete projectFixtures.assignments[key]; }); }
        else { const project = projectFixtures.projects.find(project => project.id === id)!; project.name = payload.name; project.instructions = payload.instructions || ''; data = project; }
        saveProjects();
      }
      else if (lessonDemo && /^\/courses\/\d+\/outline\/$/.test(path)) data = { status: 'completed', items: ['课程导入', '利率的基本含义', '名义利率与实际利率', '资金的时间价值', '债券价格与收益率', '期限结构', '风险溢价', '政策利率', '金融市场的联系', '案例讨论', '本节回顾', '思考与练习'].map((title, index) => ({ index, title, timestamp: index, description: index === 0 ? '本地预览示例大纲' : '' })) };
      else if (lessonDemo && /^\/courses\/\d+\/transcript\/$/.test(path)) data = { status: 'completed', segments: [], full_text: '' };
      else if (lessonDemo && /^\/courses\/\d+\/progress\/$/.test(path)) data = { elo_added: 0 };
      else if (/^\/courses\/\d+\/$/.test(path)) data = { ...courses.find(c => c.id === Number(path.split('/')[2])), video_file: lessonDemo ? '/demos/demo-knowledge.mp4' : null, ...(lessonDemo ? { ai_outline_enabled: true, courseware: 'data:text/plain,UniMind%20local%20preview%20courseware', reference_materials: 'data:text/plain,UniMind%20local%20preview%20references', description: '本地预览示例课程。视频使用仓库已有的产品演示素材，大纲与资料均为示例数据。' } : {}) };
      else if (/^\/courses\/\d+\/watch-later\/$/.test(path)) { const course = Number(path.split('/')[2]); if (config.method === 'delete') { const index = watchLater.findIndex(item => item.course === course); if (index >= 0) watchLater.splice(index, 1); } else { const item = { course, created_at: new Date().toISOString() }; if (!watchLater.some(item => item.course === course)) watchLater.push(item); data = item; } }
      else if (/^\/courses\/albums\/\d+\/courses\/$/.test(path)) data = courses;
      else if (/^\/articles\/\d+\/$/.test(path)) data = articles[0];
      else if (/^\/users\/plans\/\d+\/$/.test(path)) { const plan = plans.find(p => p.id === Number(path.split('/')[3])); if (plan && payload) Object.assign(plan, payload); data = plan; }
      else throw new AxiosError('此操作需要连接真实后端', 'PREVIEW_UNAVAILABLE', config, undefined, { data: { detail: '此操作需要连接真实后端' }, status: 501, statusText: 'Preview', headers: {}, config });
  }
  return { data: structuredClone(data), status: 200, statusText: 'OK', headers: {}, config };
};
const realFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.href);
  if (url.pathname === '/api/ai/chat/stream/') {
    const payload = JSON.parse(String(init?.body || '{}'));
    if (!(payload.conversation_id in projectFixtures.assignments)) projectFixtures.assignments[payload.conversation_id] = payload.project_id ?? null;
    saveProjects();
    const visual = { type: 'data_card', payload: { title: '复习进度', items: [{ label: '待复习', value: '8 题' }, { label: '本周练习', value: '42 题' }] } };
    const answer = '先完成到期复习，再检查薄弱知识点。\n\n这是本地示例回复，可以继续输入、切换会话或新建对话。';
    const runId = 'run-preview';
    history.push({ id: Date.now(), role: 'user', content: payload.message, timestamp: new Date().toISOString(), conversation_id: payload.conversation_id, conversation_project: projectFixtures.assignments[payload.conversation_id], conversation_title: payload.message.slice(0, 20) }, { id: Date.now() + 1, role: 'assistant', content: answer, timestamp: new Date().toISOString(), conversation_id: payload.conversation_id, conversation_project: projectFixtures.assignments[payload.conversation_id], conversation_title: payload.message.slice(0, 20), metadata: { all_visuals: [visual] } });
    const events = [
      { type: 'step', run_id: runId, name: 'get_learning_stats', status: 'queued', call_id: 'fixture-stats', round: 1, label: '查看学习进度' },
      { type: 'step', run_id: runId, name: 'get_learning_stats', status: 'running', call_id: 'fixture-stats', round: 1, label: '查看学习进度' },
      { type: 'step', run_id: runId, name: 'get_learning_stats', status: 'succeeded', call_id: 'fixture-stats', round: 1, label: '查看学习进度', result_summary: '待复习 8 题' },
      { type: 'step', run_id: runId, name: 'render_visual', status: 'queued', call_id: 'fixture-visual', round: 2, label: '复习进度' },
      { type: 'step', run_id: runId, name: 'render_visual', status: 'running', call_id: 'fixture-visual', round: 2, label: '复习进度' },
      { type: 'step', run_id: runId, name: 'render_visual', status: 'succeeded', call_id: 'fixture-visual', round: 2, label: '复习进度', visual },
      { done: true, run_id: runId, full_content: answer, conversation_title: payload.message.slice(0, 20), message_id: history[history.length - 1].id, metadata: { all_visuals: [visual] } },
    ];
    return new Response(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } });
  }
  if (url.pathname.startsWith('/api/')) return new Response('{}', { status: 404 });
  return realFetch(input, init);
};
