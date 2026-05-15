import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  ChevronLeft, Play, Calendar, BookOpen,
  Share2, Star, FileText, Download,
  ListVideo, Layers, Sparkles,
} from 'lucide-react';
import api from '@/lib/api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useAuthStore } from '@/store/useAuthStore';
import { OutlinePanel } from '@/components/course/OutlinePanel';
import { SubtitlesOverlay } from '@/components/course/SubtitlesOverlay';
import { toast } from 'sonner';

export const VideoLesson: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { updateUser } = useAuthStore();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [course, setCourse] = useState<any>(null);
  const [relatedCourses, setRelatedCourses] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasAwarded, setHasAwarded] = useState(false);
  const courseId = Number(id);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setHasAwarded(false);
        const res = await api.get(`/courses/${courseId}/`);
        setCourse(res.data);

        if (res.data.album) {
          const allRes = await api.get('/courses/');
          setRelatedCourses(allRes.data.filter((c: any) => c.album === res.data.album && c.id !== res.data.id));
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
        toast.success(`观看完成！奖励 ${res.data.elo_added} ELO`, {
          description: `当前积分: ${res.data.new_score}`
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
    if (Math.floor(video.currentTime) % 10 === 0) {
      api.post(`/courses/${courseId}/progress/`, { position: video.currentTime }).catch(() => {});
    }
  };

  if (loading) return (
    <div className="h-screen flex flex-col items-center justify-center gap-4 text-center bg-background">
      <div className="h-10 w-10 border-4 border-border border-t-primary rounded-full animate-spin" />
      <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">加载课程...</p>
    </div>
  );

  if (!course) return <div className="h-screen flex items-center justify-center font-bold">课程未找到</div>;

  return (
    <div className="max-w-[1600px] mx-auto space-y-8 animate-in fade-in duration-700 text-left p-6">
      <header className="flex items-center justify-between border-b border-border pb-6">
        <div className="flex items-center gap-6">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="rounded-xl hover:bg-muted shadow-sm border border-border h-12 w-12">
            <ChevronLeft className="h-6 w-6"/>
          </Button>
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">{course.title}</h2>
            <div className="flex items-center gap-4 opacity-40 font-bold text-[10px] uppercase tracking-widest leading-none mt-1">
               {course.album && <span className="flex items-center gap-1.5 text-foreground"><Layers className="w-3 h-3"/> {course.album}</span>}
               <span className="flex items-center gap-1.5"><Calendar className="w-3 h-3"/> {new Date(course.created_at).toLocaleDateString('zh-CN')}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-3">
           <Button variant="outline" className="rounded-xl font-bold h-11 border-border hover:bg-muted transition-all shadow-sm"><Share2 className="h-4 w-4 mr-2"/> 分享</Button>
           <Button variant="outline" className="rounded-xl font-bold h-11 border-border hover:bg-muted transition-all shadow-sm text-amber-500"><Star className="h-4 w-4 mr-2"/> 收藏</Button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        {/* Left: Video + AI Tools */}
        <div className="lg:col-span-9 space-y-8">
           <div className="bg-black overflow-hidden relative aspect-video flex items-center justify-center rounded-[2rem] shadow-2xl">
             {course.video_file ? (
               <>
               <video
                 ref={videoRef}
                 onEnded={handleVideoEnd}
                 onTimeUpdate={handleTimeUpdate}
                 src={course.video_file}
                 controls
                 className="w-full h-full"
                 preload="metadata"
                 poster={course.cover_image || undefined}
               />
               <SubtitlesOverlay courseId={courseId} videoRef={videoRef} />
               </>
             ) : (
               <div className="flex flex-col items-center gap-4 opacity-20"><div className="h-24 w-24 rounded-full border-4 border-white/10 flex items-center justify-center"><Play className="h-10 w-10 text-white fill-white"/></div><p className="text-xs font-bold uppercase tracking-widest">暂无视频</p></div>
             )}
           </div>

          {/* AI 智能大纲 */}
          <Card className="border-none shadow-sm rounded-3xl bg-card p-6">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-4 w-4 text-indigo-500" />
              <h3 className="text-sm font-bold text-foreground">AI 智能大纲</h3>
              <span className="text-[10px] text-muted-foreground ml-auto">由 ASR 语音识别 + AI 自动生成</span>
            </div>
            <OutlinePanel courseId={courseId} videoRef={videoRef} />
          </Card>

          {/* Course info + downloads */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
             <div className="md:col-span-2 space-y-8">
                <section className="space-y-6">
                   <div className="flex items-center gap-3 border-b border-border pb-4"><BookOpen className="h-5 w-5 text-emerald-600"/><h3 className="text-xl font-bold text-foreground">课程简介</h3></div>
                   <p className="text-muted-foreground text-base font-medium leading-relaxed whitespace-pre-wrap">{course.description}</p>
                </section>

                <section className="space-y-4">
                   <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">教学资源下载</h4>
                   <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {course.courseware && (
                        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm flex items-center justify-between group hover:border-foreground/20 transition-all">
                           <div className="flex items-center gap-4 text-left"><div className="h-10 w-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center"><FileText className="w-5 h-5"/></div><div><p className="text-xs font-bold truncate w-32">教学课件</p><p className="text-[9px] font-bold opacity-30 uppercase">PDF</p></div></div>
                           <Button asChild variant="ghost" size="icon" className="rounded-full"><a href={course.courseware} download><Download className="w-4 h-4"/></a></Button>
                        </div>
                      )}
                      {course.reference_materials && (
                        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm flex items-center justify-between group hover:border-foreground/20 transition-all">
                           <div className="flex items-center gap-4 text-left"><div className="h-10 w-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center"><BookOpen className="w-5 h-5"/></div><div><p className="text-xs font-bold truncate w-32">参考文献</p><p className="text-[9px] font-bold opacity-30 uppercase">PDF</p></div></div>
                           <Button asChild variant="ghost" size="icon" className="rounded-full"><a href={course.reference_materials} download><Download className="w-4 h-4"/></a></Button>
                        </div>
                      )}
                   </div>
                </section>
             </div>
             <div className="space-y-6">
                <Card className="border-none shadow-sm rounded-3xl bg-card p-8 space-y-6 text-left">
                   <div className="space-y-1"><h4 className="text-xs font-bold uppercase tracking-widest text-foreground">学习奖励</h4><p className="text-2xl font-bold text-green-700">+{course.elo_reward} ELO</p></div>
                   <p className="text-xs font-medium text-muted-foreground leading-relaxed">完整观看后自动结算并同步至您的学术分位。</p>
                </Card>
             </div>
          </div>
        </div>

        {/* Right Side: Album & Related */}
        <div className="lg:col-span-3 space-y-6">
           <div className="flex items-center justify-between px-2"><h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">同专辑系列</h4><ListVideo className="w-4 h-4 opacity-40"/></div>
           <ScrollArea className="h-[750px] pr-4">
              <div className="space-y-3">
                 {relatedCourses.map((c, i) => (
                   <Link key={c.id} to={`/course/${c.id}`}>
                     <div className="p-4 rounded-2xl border bg-transparent border-transparent hover:bg-card hover:border-border hover:shadow-md transition-all text-left mb-2 group">
                        <div className="aspect-video bg-slate-100 rounded-xl mb-3 overflow-hidden">
                           {c.cover_image && <img src={c.cover_image} alt={c.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />}
                        </div>
                        <div className="space-y-1">
                           <span className="text-[9px] font-bold opacity-30 uppercase">第 {i+1} 课</span>
                           <p className="text-xs font-bold leading-relaxed text-foreground line-clamp-2">{c.title}</p>
                        </div>
                     </div>
                   </Link>
                 ))}
                 {relatedCourses.length === 0 && <div className="py-20 text-center text-muted-foreground italic text-[10px] font-bold uppercase">暂未收录其他课程</div>}
              </div>
           </ScrollArea>
        </div>
      </div>
    </div>
  );
};