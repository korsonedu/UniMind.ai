/**
 * 班级管理 — 创建/编辑/删除班级，添加/移除学员。
 */
import { useEffect, useState } from 'react';
import { Plus, Trash, Pencil, X, Users, BookOpen } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface StudentRef {
  id: number;
  name: string;
}

interface CourseRef {
  id: number;
  title: string;
}

interface ClassData {
  id: number;
  name: string;
  student_count: number;
  students: StudentRef[];
  created_at: string;
}

interface ClassCourseRef {
  id: number;
  class_obj: number;
  course: CourseRef;
  order: number;
}

export const ClassSection: React.FC = () => {
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [loading, setLoading] = useState(true);

  // Create/edit state
  const [newName, setNewName] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');

  // Student management state
  const [manageClassId, setManageClassId] = useState<number | null>(null);
  const [availableStudents, setAvailableStudents] = useState<StudentRef[]>([]);
  const [searchStudent, setSearchStudent] = useState('');

  // Course management state
  const [courseClassId, setCourseClassId] = useState<number | null>(null);
  const [classCourses, setClassCourses] = useState<ClassCourseRef[]>([]);
  const [availableCourses, setAvailableCourses] = useState<CourseRef[]>([]);
  const [searchCourse, setSearchCourse] = useState('');

  const fetchClasses = async () => {
    setLoading(true);
    try {
      const res = await api.get('/users/institution/me/classes/');
      setClasses(res.data || []);
    } catch { toast.error('加载班级列表失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchClasses(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await api.post('/users/institution/me/classes/', { name: newName.trim() });
      setNewName('');
      toast.success(`班级「${newName.trim()}」已创建`);
      fetchClasses();
    } catch (e: any) {
      toast.error(e?.response?.data?.error || '创建失败');
    }
  };

  const handleRename = async (id: number) => {
    if (!editName.trim()) return;
    try {
      await api.put(`/users/institution/me/classes/${id}/`, { name: editName.trim() });
      setEditId(null);
      toast.success('班级名称已更新');
      fetchClasses();
    } catch (e: any) {
      toast.error(e?.response?.data?.error || '重命名失败');
    }
  };

  const handleDelete = async (c: ClassData) => {
    if (!confirm(`确定删除班级「${c.name}」？此操作不可撤销。`)) return;
    try {
      await api.delete(`/users/institution/me/classes/${c.id}/`);
      toast.success(`班级「${c.name}」已删除`);
      fetchClasses();
    } catch { toast.error('删除失败'); }
  };

  const openManage = async (c: ClassData) => {
    setManageClassId(c.id);
    try {
      // Fetch all institution students
      const res = await api.get('/users/institution/me/students/', { params: { page_size: 200 } });
      const allStudents: StudentRef[] = (res.data?.results || []).map((s: any) => ({
        id: s.id,
        name: s.nickname || s.username || `#${s.id}`,
      }));
      setAvailableStudents(allStudents);
    } catch { setAvailableStudents([]); }
  };

  const classData = classes.find(c => c.id === manageClassId);
  const memberIds = new Set(classData?.students.map(s => s.id) || []);

  const handleToggleStudent = async (sid: number, isMember: boolean) => {
    if (!manageClassId) return;
    try {
      await api.post(`/users/institution/me/classes/${manageClassId}/students/`, {
        action: isMember ? 'remove' : 'add',
        student_ids: [sid],
      });
      fetchClasses();
      // Re-open with fresh data
      const updated = classes.find(c => c.id === manageClassId);
      if (updated) openManage(updated);
    } catch { toast.error('操作失败'); }
  };

  // ── Course management ──
  const openCourseManager = async (c: ClassData) => {
    setCourseClassId(c.id);
    try {
      // fetch assigned courses
      const ccRes = await api.get('/users/institution/me/class-courses/', { params: { class_id: c.id } });
      setClassCourses(ccRes.data || []);
      // fetch all institution courses
      const courseRes = await api.get('/courses/');
      setAvailableCourses((courseRes.data?.results || courseRes.data || []).map((co: any) => ({
        id: co.id,
        title: co.title,
      })));
    } catch {
      toast.error('加载课程列表失败');
      setAvailableCourses([]);
    }
  };

  const handleToggleCourse = async (courseId: number, isAssigned: boolean) => {
    if (!courseClassId) return;
    try {
      if (isAssigned) {
        const cc = classCourses.find(cc => cc.course.id === courseId);
        if (cc) await api.delete(`/users/institution/me/class-courses/${cc.id}/`);
      } else {
        await api.post('/users/institution/me/class-courses/', {
          class_id: courseClassId,
          course_id: courseId,
          order: 0,
        });
      }
      // refresh
      const ccRes = await api.get('/users/institution/me/class-courses/', { params: { class_id: courseClassId } });
      setClassCourses(ccRes.data || []);
    } catch { toast.error('操作失败'); }
  };

  const filteredStudents = searchStudent
    ? availableStudents.filter(s => s.name.includes(searchStudent))
    : availableStudents;

  const filteredCourses = searchCourse
    ? availableCourses.filter(c => c.title.toLowerCase().includes(searchCourse.toLowerCase()))
    : availableCourses;
  const assignedCourseIds = new Set(classCourses.map(cc => cc.course.id));

  return (
    <div className="space-y-4">
      {/* ── Create bar ── */}
      <div className="flex items-center gap-2">
        <Input
          placeholder="新班级名称（如：高三1班）"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleCreate(); }}
          className="max-w-xs"
        />
        <Button size="sm" onClick={handleCreate} disabled={!newName.trim()}>
          <Plus className="h-4 w-4 mr-1" /> 创建班级
        </Button>
      </div>

      {/* ── Class list ── */}
      {loading ? (
        <p className="text-sm text-muted-foreground">加载中...</p>
      ) : classes.length === 0 ? (
        <div className="rounded-xl border border-border bg-card/50 p-8 text-center">
          <Users className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
          <p className="text-sm text-muted-foreground">暂无班级</p>
          <p className="text-xs text-muted-foreground/60 mt-0.5">创建班级后可为学员分组，布置作业时可指定班级</p>
        </div>
      ) : (
        <div className="space-y-1">
          {classes.map(c => (
            <div key={c.id} className="flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-card group">
              {editId === c.id ? (
                <Input
                  value={editName}
                  onChange={e => setEditName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleRename(c.id); }}
                  className="flex-1"
                  autoFocus
                />
              ) : (
                <span className="flex-1 text-sm font-bold">{c.name}</span>
              )}
              <span className="text-xs text-muted-foreground">{c.student_count} 名学员</span>
              {editId === c.id ? (
                <>
                  <Button size="sm" variant="ghost" onClick={() => handleRename(c.id)}>保存</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditId(null)}>
                    <X className="h-4 w-4" />
                  </Button>
                </>
              ) : (
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button size="sm" variant="ghost" onClick={() => openCourseManager(c)}>
                    <BookOpen className="h-3.5 w-3.5 mr-1" />课程
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => openManage(c)}>
                    <Users className="h-3.5 w-3.5 mr-1" />学员
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { setEditId(c.id); setEditName(c.name); }}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => handleDelete(c)}>
                    <Trash className="h-3.5 w-3.5 text-red-500" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Student Management Overlay ── */}
      {manageClassId && classData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setManageClassId(null)}>
          <div className="bg-card rounded-2xl border border-border shadow-xl w-full max-w-md max-h-[70vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <span className="text-sm font-bold">{classData.name} · 学员管理</span>
              <button onClick={() => setManageClassId(null)} className="p-1 rounded hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-3 border-b border-border">
              <Input
                placeholder="搜索学员..."
                value={searchStudent}
                onChange={e => setSearchStudent(e.target.value)}
                className="h-8 text-sm"
              />
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {filteredStudents.map(s => (
                <button
                  key={s.id}
                  onClick={() => handleToggleStudent(s.id, memberIds.has(s.id))}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors text-left',
                    memberIds.has(s.id)
                      ? 'bg-primary/10 text-primary font-bold'
                      : 'hover:bg-muted/50 text-foreground/70'
                  )}
                >
                  <span className="flex-1">{s.name}</span>
                  <span className={cn(
                    'text-[10px] font-bold px-1.5 py-0.5 rounded-full',
                    memberIds.has(s.id)
                      ? 'bg-primary/20 text-primary'
                      : 'text-muted-foreground'
                  )}>
                    {memberIds.has(s.id) ? '已加入' : '添加'}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Course Management Overlay ── */}
      {courseClassId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setCourseClassId(null)}>
          <div className="bg-card rounded-2xl border border-border shadow-xl w-full max-w-md max-h-[70vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <span className="text-sm font-bold">课程分配 · {classes.find(c => c.id === courseClassId)?.name || ''}</span>
              <button onClick={() => setCourseClassId(null)} className="p-1 rounded hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-3 border-b border-border">
              <Input
                placeholder="搜索课程..."
                value={searchCourse}
                onChange={e => setSearchCourse(e.target.value)}
                className="h-8 text-sm"
              />
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {filteredCourses.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">暂无课程</p>
              ) : (
                filteredCourses.map(co => (
                  <button
                    key={co.id}
                    onClick={() => handleToggleCourse(co.id, assignedCourseIds.has(co.id))}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors text-left',
                      assignedCourseIds.has(co.id)
                        ? 'bg-primary/10 text-primary font-bold'
                        : 'hover:bg-muted/50 text-foreground/70'
                    )}
                  >
                    <BookOpen className="h-3.5 w-3.5 shrink-0" />
                    <span className="flex-1 truncate">{co.title}</span>
                    <span className={cn(
                      'text-[10px] font-bold px-1.5 py-0.5 rounded-full',
                      assignedCourseIds.has(co.id)
                        ? 'bg-primary/20 text-primary'
                        : 'text-muted-foreground'
                    )}>
                      {assignedCourseIds.has(co.id) ? '已分配' : '添加'}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
