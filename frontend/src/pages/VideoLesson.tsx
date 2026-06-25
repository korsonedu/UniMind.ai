import React, { useState, useEffect, useRef } from 'react';
import { flushSync } from 'react-dom';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CaretLeft, Play, Pause, Calendar, BookOpen, ShareNetwork, Star, FileText, Download, Playlist, Stack, Sparkle, ArrowsOut, ArrowsIn, ClosedCaptioning, SpeakerHigh, SpeakerX } from '@phosphor-icons/react';
import api from '@/lib/api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useAuthStore } from '@/store/useAuthStore';
import { OutlinePanel } from '@/components/course/OutlinePanel';
import { SubtitlesOverlay } from '@/components/course/SubtitlesOverlay';
import { toast } from 'sonner';

const formatTime = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
};

export const VideoLesson: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation('videoLesson');
  const updateUser = useAuthStore(s => s.updateUser);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoContainerRef = useRef<HTMLDivElement | null>(null);
  const [course, setCourse] = useState<any>(null);
  const [relatedCourses, setRelatedCourses] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasAwarded, setHasAwarded] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [subtitlesVisible, setSubtitlesVisible] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [seeking] = useState(false);
  const hideControlsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressRef = useRef<HTMLDivElement | null>(null);
  const courseId = Number(id);

  const SPEEDS = [1, 1.25, 1.5, 2];

  useEffect(() => {
    const onFSChange = () => {
      const isFS = !!document.fullscreenElement;
      setIsFullscreen(isFS);
      // 退出全屏时解锁方向（进入时的 lock 在 toggleFullscreen 手势上下文里调用）
      if (!isFS) {
        try { screen.orientation?.unlock?.(); } catch {}
      }
    };
    // iOS Safari webkit 全屏事件（原生播放器自动处理横屏）
    const onWebkitFSEnter = () => setIsFullscreen(true);
    const onWebkitFSExit = () => setIsFullscreen(false);
    document.addEventListener('fullscreenchange', onFSChange);
    document.addEventListener('webkitbeginfullscreen', onWebkitFSEnter);
    document.addEventListener('webkitendfullscreen', onWebkitFSExit);
    return () => {
      document.removeEventListener('fullscreenchange', onFSChange);
      document.removeEventListener('webkitbeginfullscreen', onWebkitFSEnter);
      document.removeEventListener('webkitendfullscreen', onWebkitFSExit);
    };
  }, []);

  const scheduleHideControls = () => {
    if (hideControlsTimer.current) clearTimeout(hideControlsTimer.current);
    hideControlsTimer.current = setTimeout(() => setShowControls(false), 3000);
  };

  const handleVideoInteraction = () => {
    setShowControls(true);
    scheduleHideControls();
  };

  const toggleFullscreen = async () => {
    const v = videoRef.current;
    // 退出全屏（标准全屏或 iOS Safari webkit 全屏）
    if (document.fullscreenElement || (v as any)?.webkitDisplayingFullscreen) {
      document.exitFullscreen().catch(() => {});
      (v as any)?.webkitExitFullscreen?.();
      return;
    }
    if (!v) return;
    // iOS Safari：使用原生播放器全屏，自动处理横屏
    if ((v as any).webkitEnterFullscreen) {
      (v as any).webkitEnterFullscreen();
      return;
    }
    // 标准浏览器：全屏容器 div 使视频可自由撑满
    const container = videoContainerRef.current;
    if (!container) return;
    flushSync(() => setIsFullscreen(true));
    try {
      await container.requestFullscreen();
      // 紧跟在 requestFullscreen 后锁横屏，必须在此处（用户手势上下文中）调用
      try { await (screen.orientation as any)?.lock?.('landscape'); } catch {}
    } catch {
      setIsFullscreen(false);
    }
  };

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setIsMuted(v.muted);
  };

  const cycleSpeed = () => {
    const v = videoRef.current;
    if (!v) return;
    const idx = SPEEDS.indexOf(playbackRate);
    const next = SPEEDS[(idx + 1) % SPEEDS.length];
    v.playbackRate = next;
    setPlaybackRate(next);
  };

  // 同步 video 初始状态
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    setIsMuted(v.muted);
    setPlaybackRate(v.playbackRate);
  }, [course?.video_file]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setHasAwarded(false);
        const res = await api.get(`/courses/${courseId}/`);
        setCourse(res.data);

        if (res.data.album) {
          const albumRes = await api.get(`/courses/albums/${res.data.album.id}/courses/`);
          setRelatedCourses(albumRes.data.filter((c: any) => c.id !== res.data.id));
        }
      } catch (e) { console.error('fetchCourse failed', e); }
      finally { setLoading(false); }
    };
    fetchData();
  }, [courseId]);

  const handleVideoEnd = async () => {
    if (hasAwarded) return;
    try {
      const res = await api.post(`/courses/${courseId}/progress/`, { is_finished: true });
      if (res.data.elo_added > 0) {
        setHasAwarded(true);
        toast.success(t('watchComplete', { elo: res.data.elo_added }), {
          description: t('currentPoints', { score: res.data.new_score })
        });
        const me = await api.get('/users/me/');
        updateUser(me.data);
      }
    } catch (e) {
      console.error("Failed to update progress/award ELO", e);
    }
  };

  const handleTimeUpdate = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const video = e.currentTarget;
    if (!seeking) setCurrentTime(video.currentTime);
    if (Math.floor(video.currentTime) % 10 === 0) {
      api.post(`/courses/${courseId}/progress/`, { position: video.currentTime }).catch(() => {});
    }
  };

  const handleLoadedMetadata = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    setDuration(e.currentTarget.duration || 0);
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const bar = progressRef.current;
    const v = videoRef.current;
    if (!bar || !v || !duration) return;
    const rect = bar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const t = ratio * duration;
    v.currentTime = t;
    setCurrentTime(t);
  };

  if (loading) return (
    <div className="min-h-dvh flex flex-col items-center justify-center gap-4 text-center bg-background">
      <div className="h-10 w-10 border-4 border-border border-t-primary rounded-full animate-spin" />
      <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">{t('loading')}</p>
    </div>
  );

  if (!course) return <div className="min-h-dvh flex items-center justify-center font-bold">{t('notFound')}</div>;

  return (
    <div className="animate-in fade-in duration-700 text-left">
      {/* 视频播放器 — 移动端左右顶到头，桌面端有 max-w 约束 */}
      <div className="lg:max-w-[1600px] lg:mx-auto lg:px-6">
        <div
          ref={videoContainerRef}
          className={isFullscreen ? 'fixed inset-0 z-50 bg-black' : 'bg-black overflow-hidden relative flex items-center justify-center shadow-lg group lg:rounded-2xl'}
          onMouseMove={handleVideoInteraction}
          onMouseLeave={() => setShowControls(false)}
          onTouchStart={handleVideoInteraction}
        >
          {course.video_file ? (
            <>
            <video
              ref={videoRef}
              playsInline
              onEnded={handleVideoEnd}
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={handleLoadedMetadata}
              onPlay={() => { setIsPlaying(true); scheduleHideControls(); }}
              onPause={() => { setIsPlaying(false); setShowControls(true); }}
              onClick={() => { videoRef.current?.paused ? videoRef.current?.play() : videoRef.current?.pause(); }}
              src={course.video_file}
              className={isFullscreen ? 'absolute inset-0 w-full h-full object-contain' : 'w-full lg:max-h-[70vh] cursor-pointer'}
              preload="metadata"
              poster={course.cover_image || undefined}
            />
            <SubtitlesOverlay courseId={courseId} videoRef={videoRef} visible={subtitlesVisible} />
            {/* 自定义控制栏：全屏/非全屏均保留 */}
            <div className={`absolute bottom-0 inset-x-0 z-20 px-3 pb-3 pt-8 bg-gradient-to-t from-black/70 via-black/30 to-transparent transition-opacity duration-300 ${showControls ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
              <div ref={progressRef} onClick={handleSeek} className="w-full h-5 flex items-center cursor-pointer group/progress mb-1">
                <div className="w-full h-1 rounded-full bg-white/20 group-hover/progress:h-1.5 transition-all">
                  <div className="h-full rounded-full bg-white transition-all" style={{ width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%` }} />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-white/70 tabular-nums">{formatTime(currentTime)} / {formatTime(duration)}</span>
                <div className="flex items-center gap-0.5">
                  <button
                    onClick={() => { videoRef.current?.paused ? videoRef.current?.play() : videoRef.current?.pause(); }}
                    className="rounded-md p-1.5 text-white/70 hover:text-white transition-colors"
                    aria-label={isPlaying ? t('pause') : t('play')}
                    title={isPlaying ? t('pause') : t('play')}
                  >
                    {isPlaying ? <Pause className="h-[18px] w-[18px]" /> : <Play className="h-[18px] w-[18px]" />}
                  </button>
                  <button onClick={toggleMute} className="rounded-md p-1.5 text-white/70 hover:text-white transition-colors" aria-label={isMuted ? t('unmute') : t('mute')} title={isMuted ? t('unmute') : t('mute')}>
                    {isMuted ? <SpeakerX className="h-[18px] w-[18px]" /> : <SpeakerHigh className="h-[18px] w-[18px]" />}
                  </button>
                  <button onClick={cycleSpeed} className="rounded-md px-1.5 py-1 text-xs font-bold text-white/70 hover:text-white transition-colors min-w-[32px] text-center" aria-label={t('playbackSpeed')} title={t('playbackSpeed')}>
                    {playbackRate}x
                  </button>
                  <button onClick={() => setSubtitlesVisible(v => !v)} className={`rounded-md p-1.5 transition-colors ${subtitlesVisible ? 'bg-white/20 text-white' : 'text-white/70 hover:text-white'}`} aria-label={subtitlesVisible ? t('hideSubtitles') : t('showSubtitles')} title={subtitlesVisible ? t('hideSubtitles') : t('showSubtitles')}>
                    <ClosedCaptioning className="h-[18px] w-[18px]" />
                  </button>
                  <button onClick={toggleFullscreen} className="rounded-md p-1.5 text-white/70 hover:text-white transition-colors" aria-label={isFullscreen ? t('exitFullscreen') : t('fullscreen')} title={isFullscreen ? t('exitFullscreen') : t('fullscreen')}>
                    {isFullscreen ? <ArrowsIn className="h-[18px] w-[18px]" /> : <ArrowsOut className="h-[18px] w-[18px]" />}
                  </button>
                </div>
              </div>
            </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-4 opacity-20 py-24"><div className="h-24 w-24 rounded-full border-4 border-white/10 flex items-center justify-center"><Play className="h-10 w-10 text-white fill-white"/></div><p className="text-xs font-bold uppercase tracking-widest">{t('noVideo')}</p></div>
          )}
        </div>
      </div>

      {/* 视频下方内容 */}
      <div className="max-w-[1600px] mx-auto space-y-8 p-6">
        <header className="flex items-center justify-between border-b border-border pb-6">
          <div className="flex items-center gap-6">
            <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="rounded-xl hover:bg-muted shadow-sm border border-border h-12 w-12">
              <CaretLeft className="h-6 w-6"/>
            </Button>
            <div>
              <h2 className="text-3xl font-bold tracking-tight text-foreground">{course.title}</h2>
              <div className="flex items-center gap-4 opacity-40 font-bold text-[10px] uppercase tracking-widest leading-none mt-1">
                 {course.album && <span className="flex items-center gap-1.5 text-foreground"><Stack className="w-3 h-3"/> {course.album.name}</span>}
                 <span className="flex items-center gap-1.5"><Calendar className="w-3 h-3"/> {new Date(course.created_at).toLocaleDateString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}</span>
              </div>
            </div>
          </div>
          <div className="flex gap-3">
             <Button variant="outline" className="rounded-xl font-bold h-11 border-border hover:bg-muted transition-all shadow-sm"><ShareNetwork className="h-4 w-4 mr-2"/> {t('share')}</Button>
             <Button variant="outline" className="rounded-xl font-bold h-11 border-border hover:bg-muted transition-all shadow-sm text-amber-500"><Star className="h-4 w-4 mr-2"/> {t('favorite')}</Button>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          {/* Left: AI Tools + Course Info */}
          <div className="lg:col-span-9 space-y-8">
            {/* AI 智能大纲 */}
            <Card className="border-none shadow-sm rounded-3xl bg-card p-6">
              <div className="flex items-center gap-2 mb-3">
                <Sparkle className="h-4 w-4 text-indigo-500" />
                <h3 className="text-sm font-bold text-foreground">{t('aiOutline')}</h3>
              </div>
              <OutlinePanel courseId={courseId} videoRef={videoRef} />
            </Card>

            {/* Course info + downloads */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
               <div className="md:col-span-2 space-y-8">
                  <section className="space-y-6">
                     <div className="flex items-center gap-3 border-b border-border pb-4"><BookOpen className="h-5 w-5 text-emerald-600"/><h3 className="text-xl font-bold text-foreground">{t('courseIntro')}</h3></div>
                     <p className="text-muted-foreground text-base font-medium leading-relaxed whitespace-pre-wrap">{course.description}</p>
                  </section>

                  <section className="space-y-4">
                     <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{t('teachingResources')}</h4>
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {course.courseware && (
                          <div className="p-5 rounded-2xl bg-card border border-border shadow-sm flex items-center justify-between group hover:border-foreground/20 transition-all">
                             <div className="flex items-center gap-4 text-left"><div className="h-10 w-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center"><FileText className="w-5 h-5"/></div><div><p className="text-xs font-bold truncate w-32">{t('courseware')}</p><p className="text-[9px] font-bold opacity-30 uppercase">PDF</p></div></div>
                             <Button asChild variant="ghost" size="icon" className="rounded-full"><a href={course.courseware} download><Download className="w-4 h-4"/></a></Button>
                          </div>
                        )}
                        {course.reference_materials && (
                          <div className="p-5 rounded-2xl bg-card border border-border shadow-sm flex items-center justify-between group hover:border-foreground/20 transition-all">
                             <div className="flex items-center gap-4 text-left"><div className="h-10 w-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center"><BookOpen className="w-5 h-5"/></div><div><p className="text-xs font-bold truncate w-32">{t('references')}</p><p className="text-[9px] font-bold opacity-30 uppercase">PDF</p></div></div>
                             <Button asChild variant="ghost" size="icon" className="rounded-full"><a href={course.reference_materials} download><Download className="w-4 h-4"/></a></Button>
                          </div>
                        )}
                     </div>
                  </section>
               </div>
               <div className="space-y-6">
                  <Card className="border-none shadow-sm rounded-3xl bg-card p-8 space-y-6 text-left">
                     <div className="space-y-1"><h4 className="text-xs font-bold uppercase tracking-widest text-foreground">{t('learningReward')}</h4><p className="text-2xl font-bold text-green-700">+{course.elo_reward} ELO</p></div>
                     <p className="text-xs font-medium text-muted-foreground leading-relaxed">{t('rewardDesc')}</p>
                  </Card>
               </div>
            </div>
          </div>

          {/* Right Side: Album & Related */}
          <div className="lg:col-span-3 space-y-6">
             <div className="flex items-center justify-between px-2"><h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{t('sameSeries')}</h4><Playlist className="w-4 h-4 opacity-40"/></div>
             <ScrollArea className="h-[750px] pr-4">
                <div className="space-y-3">
                   {relatedCourses.map((c, i) => (
                     <Link key={c.id} to={`/course/${c.id}`}>
                       <div className="p-4 rounded-2xl border bg-transparent border-transparent hover:bg-card hover:border-border hover:shadow-md transition-all text-left mb-2 group">
                          <div className="aspect-video bg-slate-100 rounded-xl mb-3 overflow-hidden">
                             {c.cover_image && <img src={c.cover_image} alt={c.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform" loading="lazy" />}
                          </div>
                          <div className="space-y-1">
                             <span className="text-[9px] font-bold opacity-30 uppercase">{t('lessonNumber', { i: i + 1 })}</span>
                             <p className="text-xs font-bold leading-relaxed text-foreground line-clamp-2">{c.title}</p>
                          </div>
                       </div>
                     </Link>
                   ))}
                   {relatedCourses.length === 0 && <div className="py-20 text-center text-muted-foreground italic text-[10px] font-bold uppercase">{t('noRelatedCourses')}</div>}
                </div>
             </ScrollArea>
          </div>
        </div>
      </div>
    </div>
  );
};