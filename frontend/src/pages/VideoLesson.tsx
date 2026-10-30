import type { Course } from '@/types/api';
import React, { useState, useEffect, useRef } from 'react';
import { flushSync } from 'react-dom';
import { useParams } from 'react-router-dom';
import { Play, Pause, Star, FileText, Download, ArrowsOut, ArrowsIn, ClosedCaptioning, SpeakerHigh, SpeakerX } from '@phosphor-icons/react';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { OutlinePanel } from '@/components/course/OutlinePanel';
import { SubtitlesOverlay } from '@/components/course/SubtitlesOverlay';
import { toast } from 'sonner';
import { shouldTogglePlayback } from './videoLessonKeyboard';
import { useLearningSession } from '@/hooks/useLearningSession';
import { useDesktopStore } from '@/lib/desktop';
import '@/styles/course-lesson.css';

const formatTime = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
};

interface VideoLessonProps {
  isFavorite?: boolean;
  favoritePending?: boolean;
  onFavoriteChange?: () => void;
}

export const VideoLesson: React.FC<VideoLessonProps> = ({ isFavorite = false, favoritePending = false, onFavoriteChange }) => {
  const { id } = useParams();
  const updateUser = useAuthStore(s => s.updateUser);
  const desktopState = useDesktopStore(s => s.state);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoContainerRef = useRef<HTMLDivElement | null>(null);
  const [course, setCourse] = useState<Course | null>(null);
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
  const courseId = Number(id);
  const offlineDownload = desktopState?.downloads.find(item => item.courseId === courseId);
  const offlineReady = offlineDownload?.status === 'ready'
    && (!offlineDownload.expiresAt || offlineDownload.expiresAt > Date.now());
  const [offlinePending, setOfflinePending] = useState(false);

  const handleOffline = async () => {
    const desktop = window.unimindDesktop;
    if (!desktop) return;
    setOfflinePending(true);
    try {
      if (offlineReady) await desktop.openOfflineCourse(courseId);
      else useDesktopStore.setState({ state: await desktop.downloadCourse(courseId) });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '离线课程操作失败，请重试。');
    } finally {
      setOfflinePending(false);
    }
  };

  useLearningSession({ enabled: !loading && course?.id === courseId && !!course.video_file, kind: 'video', courseId, videoRef });

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !course?.video_file) return;
    let lastTick = performance.now();
    let watched = 0;
    let saving = false;
    const pending: { position: number; duration: number; watched_seconds: number; event_id: string }[] = [];
    const tick = () => {
      const now = performance.now();
      const delta = (now - lastTick) / 1000;
      if (!video.paused && !video.seeking && !video.ended && video.readyState >= 2 && delta <= 5) watched += delta;
      lastTick = now;
    };
    const flush = async () => {
      tick();
      if (watched > 0) {
        pending.push({ position: video.currentTime, duration: Number.isFinite(video.duration) ? video.duration : 0, watched_seconds: Math.min(120, watched), event_id: crypto.randomUUID() });
        watched = 0;
      }
      if (saving) return;
      saving = true;
      try { while (pending.length) { await api.post(`/courses/${courseId}/progress/`, pending[0]); pending.shift(); } }
      catch { /* Keep the same event ID for the next retry. */ }
      finally { saving = false; }
    };
    const syncPosition = () => { lastTick = performance.now(); };
    const onPause = () => { void flush(); };
    video.addEventListener('play', syncPosition);
    video.addEventListener('seeking', syncPosition);
    video.addEventListener('pause', onPause);
    const clock = window.setInterval(tick, 1000);
    const save = window.setInterval(() => { void flush(); }, 10000);
    return () => { clearInterval(clock); clearInterval(save); video.removeEventListener('play', syncPosition); video.removeEventListener('seeking', syncPosition); video.removeEventListener('pause', onPause); void flush(); };
  }, [courseId, course?.video_file, loading]);

  const SPEEDS = [1, 1.25, 1.5, 2];

  useEffect(() => {
    const onFSChange = () => {
      const isFS = !!document.fullscreenElement;
      setIsFullscreen(isFS);
      // 退出全屏时解锁方向（进入时的 lock 在 toggleFullscreen 手势上下文里调用）
      if (!isFS) {
        try { screen.orientation?.unlock?.(); } catch { /* Orientation locking is optional; fullscreen remains available. */ }
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
    const v = videoRef.current as (HTMLVideoElement & { webkitDisplayingFullscreen?: boolean; webkitExitFullscreen?: () => void; webkitEnterFullscreen?: () => void }) | null;
    // 退出全屏（标准全屏或 iOS Safari webkit 全屏）
    if (document.fullscreenElement || v?.webkitDisplayingFullscreen) {
      document.exitFullscreen().catch(() => {});
      v?.webkitExitFullscreen?.();
      return;
    }
    if (!v) return;
    // iOS Safari：使用原生播放器全屏，自动处理横屏
    if (v.webkitEnterFullscreen) {
      v.webkitEnterFullscreen();
      return;
    }
    // 标准浏览器：全屏容器 div 使视频可自由撑满
    const container = videoContainerRef.current;
    if (!container) return;
    flushSync(() => setIsFullscreen(true));
    try {
      await container.requestFullscreen();
      // 紧跟在 requestFullscreen 后锁横屏，必须在此处（用户手势上下文中）调用
      try { await (screen.orientation as ScreenOrientation & { lock?: (orientation: string) => Promise<void> })?.lock?.('landscape'); } catch { /* Orientation locking is optional; fullscreen remains available. */ }
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
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!shouldTogglePlayback(event)) return;
      const video = videoRef.current;
      if (!video) return;
      event.preventDefault();
      if (video.paused) void video.play(); else video.pause();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const fetchData = async () => {
      try {
        setLoading(true);
        setCourse(null);
        setHasAwarded(false);
        const res = await api.get(`/courses/${courseId}/`, { signal: controller.signal });
        setCourse(res.data);
      } catch (e) { if (!controller.signal.aborted) console.error('fetchCourse failed', e); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    };
    fetchData();
    return () => controller.abort();
  }, [courseId]);

  const handleVideoEnd = async () => {
    if (hasAwarded) return;
    try {
      const res = await api.post(`/courses/${courseId}/progress/`, { is_finished: true });
      if (res.data.elo_added > 0) {
        setHasAwarded(true);
        toast.success(`观看完成！奖励 ${res.data.elo_added} ELO`, {
          description: `当前 ELO: ${res.data.new_score}`
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
  };

  const handleLoadedMetadata = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const video = e.currentTarget;
    const dur = video.duration || 0;
    setDuration(dur);
    if (Number.isFinite(dur) && dur > 0) api.post(`/courses/${courseId}/progress/`, { duration: dur }).catch(() => {});
    // 续播：从上次位置继续（已完成、接近开头或结尾则不跳）
    const p = course?.progress;
    if (p && !p.is_finished && p.last_position > 10 && dur > 0 && p.last_position < dur - 10) {
      video.currentTime = p.last_position;
      setCurrentTime(p.last_position);
      toast.info('已从上次位置继续播放');
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    if (!v || !duration) return;
    const t = Number(e.target.value);
    v.currentTime = t;
    setCurrentTime(t);
  };

  if (loading) return (
    <div className="um-lesson um-lesson-state" role="status">
      <div className="h-10 w-10 border-4 border-border border-t-primary rounded-full animate-spin" />
      <p>正在加载课程…</p>
    </div>
  );

  if (!course) return <div className="um-lesson um-lesson-state">课程未找到</div>;

  return (
    <div className="um-lesson">
      <section className="um-lesson-view" aria-label="视频与课程信息">
        <div className="um-lesson-stage">
        <div
          ref={videoContainerRef}
          className="um-lesson-player"
          data-fullscreen={isFullscreen || undefined}
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
              onPause={() => {
                setIsPlaying(false);
                setShowControls(true);
                // 暂停时补存进度，避免最后 10 秒内的位置丢失
                api.post(`/courses/${courseId}/progress/`, { position: videoRef.current?.currentTime ?? 0 }).catch(() => {});
              }}
              onClick={() => { if (videoRef.current?.paused) void videoRef.current.play(); else videoRef.current?.pause(); }}
              src={course.video_file}
              className="um-lesson-video"
              preload="metadata"
              poster={course.cover_image || undefined}
            />
            <SubtitlesOverlay courseId={courseId} videoRef={videoRef} visible={subtitlesVisible} />
            <div className="um-lesson-controls" data-visible={showControls || !isPlaying || undefined}>
              <input className="um-lesson-progress" type="range" min="0" max={duration || 0} step="0.1" value={Math.min(currentTime, duration)} onChange={handleSeek} disabled={!duration} aria-label="播放进度" aria-valuetext={`${formatTime(currentTime)} / ${formatTime(duration)}`} />
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-white/70 tabular-nums">{formatTime(currentTime)} / {formatTime(duration)}</span>
                <div className="flex items-center gap-0.5">
                  <button
                    onClick={() => { if (videoRef.current?.paused) void videoRef.current.play(); else videoRef.current?.pause(); }}
                    className="rounded-md p-1.5 text-white/70 hover:text-white transition-colors"
                    aria-label={isPlaying ? '暂停' : '播放'}
                    title={isPlaying ? '暂停' : '播放'}
                  >
                    {isPlaying ? <Pause className="h-[18px] w-[18px]" /> : <Play className="h-[18px] w-[18px]" />}
                  </button>
                  <button onClick={toggleMute} className="rounded-md p-1.5 text-white/70 hover:text-white transition-colors" aria-label={isMuted ? '取消静音' : '静音'} title={isMuted ? '取消静音' : '静音'}>
                    {isMuted ? <SpeakerX className="h-[18px] w-[18px]" /> : <SpeakerHigh className="h-[18px] w-[18px]" />}
                  </button>
                  <button onClick={cycleSpeed} className="rounded-md px-1.5 py-1 text-xs font-bold text-white/70 hover:text-white transition-colors min-w-[32px] text-center" aria-label="播放速度" title="播放速度">
                    {playbackRate}x
                  </button>
                  <button onClick={() => setSubtitlesVisible(v => !v)} className={`rounded-md p-1.5 transition-colors ${subtitlesVisible ? 'bg-white/20 text-white' : 'text-white/70 hover:text-white'}`} aria-label={subtitlesVisible ? '关闭字幕' : '开启字幕'} title={subtitlesVisible ? '关闭字幕' : '开启字幕'}>
                    <ClosedCaptioning className="h-[18px] w-[18px]" />
                  </button>
                  <button onClick={toggleFullscreen} className="rounded-md p-1.5 text-white/70 hover:text-white transition-colors" aria-label={isFullscreen ? '退出全屏' : '全屏'} title={isFullscreen ? '退出全屏' : '全屏'}>
                    {isFullscreen ? <ArrowsIn className="h-[18px] w-[18px]" /> : <ArrowsOut className="h-[18px] w-[18px]" />}
                  </button>
                </div>
              </div>
            </div>
            </>
          ) : (
            <div className="um-lesson-no-video"><Play size={32} weight="light" /><p>暂无视频</p></div>
          )}
        </div>
        </div>
        <header className="um-lesson-heading">
          <div><p className="um-lesson-module">{[course.subject_name, course.module_name].filter(Boolean).join(' / ') || '待归类'}</p><h1>{course.title}</h1></div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {window.unimindDesktop && course.video_file && (
              <button className="um-lesson-favorite" disabled={offlinePending || offlineDownload?.status === 'downloading'} onClick={() => void handleOffline()} title={offlineDownload?.error}>
                {offlineReady ? <Play size={18} /> : <Download size={18} />}
                {offlineDownload?.status === 'downloading'
                  ? `下载中${offlineDownload.totalBytes > 0 ? ` ${Math.min(100, Math.floor(offlineDownload.receivedBytes / offlineDownload.totalBytes * 100))}%` : '…'}`
                  : offlineReady ? '离线播放' : offlineDownload?.status === 'paused' ? '继续下载' : offlineDownload?.status === 'failed' ? '重试下载' : offlineDownload ? '重新下载' : '下载课程'}
              </button>
            )}
            {offlineDownload?.status === 'downloading' && window.unimindDesktop?.pauseDownload && <button className="um-lesson-favorite" disabled={offlinePending} onClick={async () => {
              setOfflinePending(true);
              try { useDesktopStore.setState({ state: await window.unimindDesktop!.pauseDownload!(courseId) }); }
              catch (error) { toast.error(error instanceof Error ? error.message : '暂停失败，请重试。'); }
              finally { setOfflinePending(false); }
            }}><Pause size={18} />暂停下载</button>}
            <button className="um-lesson-favorite" disabled={favoritePending || !onFavoriteChange} onClick={onFavoriteChange} aria-pressed={isFavorite}><Star size={18} weight={isFavorite ? 'fill' : 'regular'} />{isFavorite ? '已收藏' : '收藏'}</button>
          </div>
        </header>
      </section>
      <aside className="um-lesson-sidebar" aria-label="学习侧栏">
        <section className="um-lesson-outline-section" aria-labelledby="lesson-outline-heading">
          <h2 id="lesson-outline-heading">课程大纲</h2>
          {course.ai_outline_enabled !== false ? <OutlinePanel courseId={courseId} videoRef={videoRef} /> : <p className="um-lesson-empty">本课程暂无大纲</p>}
        </section>
        <section className="um-lesson-resources" aria-labelledby="lesson-resources-heading">
          <h2 id="lesson-resources-heading">课程资料</h2>
          {course.courseware && <a href={course.courseware} download target="_blank" rel="noopener noreferrer"><FileText size={18} /><span>教学课件</span><Download size={16} /></a>}
          {course.reference_materials && <a href={course.reference_materials} download target="_blank" rel="noopener noreferrer"><FileText size={18} /><span>参考资料</span><Download size={16} /></a>}
          {!course.courseware && !course.reference_materials && <p className="um-lesson-empty">暂无课程资料</p>}
        </section>
        <section className="um-lesson-intro" aria-labelledby="lesson-intro-heading">
          <h2 id="lesson-intro-heading">课程简介</h2>
          <div className="um-lesson-description" tabIndex={0}><p>{course.description || '暂无课程简介'}</p></div>
        </section>
      </aside>
    </div>
  );
};
