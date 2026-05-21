import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PlusCircle, PlayCircle, BookOpen } from 'lucide-react';
import { useAuthStore } from '@/store/useAuthStore';
import { useNavigate, Link } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Loading } from '@/components/Loading';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { useFetch } from '@/lib/useFetch';
import api from '@/lib/api';

export const CourseCenter: React.FC = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const { t } = useTranslation('common');
  const { data: courses, loading, error, refetch } = useFetch<any[]>(
    (signal) => api.get('/courses/', { signal }).then(r => r.data)
  );

  const ActionBtn = user?.role === 'admin' ? (
    <Button
      onClick={() => navigate('/management')}
      className="bg-primary text-primary-foreground hover:opacity-90 rounded-2xl px-6 h-11 font-bold shadow-lg transition-all hover:scale-[1.02]"
    >
      <PlusCircle className="mr-2 h-4 w-4" /> {t('publishCourse')}
    </Button>
  ) : null;

  if (loading) return <Loading message="Synchronizing Catalog..." />;
  if (error) return <InlineError message={error} onRetry={refetch} />;
  if (!courses?.length) return <EmptyState icon={BookOpen} title={t('noCourses')} description={t('noCoursesHint')} className="h-[60vh]" />;

  return (
    <PageWrapper 
      title={t('pages:courseCenter.title')}
      subtitle={t('pages:courseCenter.subtitle')}
      action={ActionBtn}
    >
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 text-left animate-in fade-in duration-700">
           {courses.map(course => (
             <Link
              key={course.id}
              to={`/course/${course.id}`}
              className="border-none shadow-sm rounded-2xl overflow-hidden bg-card border border-border group hover:shadow-lg transition-[box-shadow,transform] duration-300 cursor-pointer block"
             >
                <div className="aspect-video bg-slate-100 relative overflow-hidden">
                   {course.cover_image ? (
                     <img src={course.cover_image} alt={course.title} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" />
                   ) : (
                     <div className="w-full h-full flex items-center justify-center text-muted-foreground font-bold uppercase tracking-widest text-[11px]">No Preview</div>
                   )}
                   <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <div className="h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center shadow-lg scale-75 group-hover:scale-100 transition-transform">
                        <PlayCircle className="h-4 w-4 text-foreground" />
                      </div>
                   </div>
                </div>
                <CardContent className="p-4 space-y-2">
                   <div className="flex justify-between items-start gap-2">
                      <h3 className="font-bold text-sm leading-tight group-hover:text-emerald-600 transition-colors line-clamp-1 flex-1">{course.title}</h3>
                   </div>
                   <p className="text-[11px] text-muted-foreground line-clamp-2 font-medium leading-relaxed min-h-[28px]">{course.description}</p>
                </CardContent>
             </Link>
           ))}
        </div>
    </PageWrapper>
  );
};
