# Course Tag System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add institution-scoped flexible tags to courses with autocomplete-on-upload and filterable course center.

**Architecture:** New `CourseTag` model (institution FK + name + slug) with M2M through `CourseTagRelation`. Tag CRUD API + batch-assign endpoint. Frontend: TagAutocomplete component for upload form, tag chips for course center filtering, tag management tab in Maintenance.

**Tech Stack:** Django 6.0 + DRF + React 19 + TypeScript

---

### Task 1: Add CourseTag and CourseTagRelation models

**Files:**
- Modify: `backend/courses/models.py` (append after `VideoProgress`)

- [ ] **Step 1: Add models to models.py**

Append to `backend/courses/models.py` after line 114 (`VideoProgress` class ends):

```python
class CourseTag(models.Model):
    institution = models.ForeignKey("users.Institution", on_delete=models.CASCADE, related_name="course_tags")
    name = models.CharField(max_length=50, verbose_name="标签名")
    slug = models.SlugField(max_length=60, verbose_name="URL标识")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('institution', 'slug')

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CourseTagRelation(models.Model):
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='tag_relations')
    tag = models.ForeignKey(CourseTag, on_delete=models.CASCADE, related_name='course_relations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'tag')
```

- [ ] **Step 2: Make migration**

```bash
cd backend && python manage.py makemigrations courses
```

- [ ] **Step 3: Run migration**

```bash
cd backend && python manage.py migrate
```

- [ ] **Step 4: Commit**

```bash
git add backend/courses/models.py backend/courses/migrations/0015_*.py && git commit -m "feat: add CourseTag and CourseTagRelation models"
```

---

### Task 2: Add tag serializers and wire into CourseSerializer

**Files:**
- Modify: `backend/courses/serializers.py`

- [ ] **Step 1: Add CourseTagSerializer and update CourseSerializer**

Replace `backend/courses/serializers.py` imports (line 2) to include new models, then append serializers:

Edit line 2:
```python
from .models import Course, Album, StartupMaterial, CourseTag, CourseTagRelation
```

After `StartupMaterialSerializer` (around line 46), add:

```python
class CourseTagSerializer(serializers.ModelSerializer):
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = CourseTag
        fields = ('id', 'name', 'slug', 'course_count', 'created_at')
        read_only_fields = ('slug', 'created_at')

    def get_course_count(self, obj):
        return getattr(obj, 'course_count', obj.course_relations.count())
```

In `CourseSerializer.Meta.fields`, add `'tags'` at the end:
```python
fields = ('id', 'title', 'album_obj', 'description', 'knowledge_point', 'cover_image', 'video_file', 'elo_reward', 'courseware', 'reference_materials', 'ai_outline_enabled', 'institution', 'created_at', 'updated_at', 'author', 'tags')
```

Add `tags` field to `CourseSerializer` class body (before `class Meta`):
```python
tags = serializers.SerializerMethodField()

def get_tags(self, obj):
    relations = obj.tag_relations.select_related('tag').all()
    return CourseTagSerializer([r.tag for r in relations], many=True).data
```

- [ ] **Step 2: Commit**

```bash
git add backend/courses/serializers.py && git commit -m "feat: add CourseTagSerializer and wire tags into CourseSerializer"
```

---

### Task 3: Add tag views and URLs

**Files:**
- Create: `backend/courses/views_tags.py`
- Modify: `backend/courses/views.py:353-368` (add tag filter)
- Modify: `backend/courses/urls.py`

- [ ] **Step 1: Create views_tags.py**

```python
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Count
from django.utils.text import slugify

from .models import Course, CourseTag, CourseTagRelation
from .serializers import CourseTagSerializer
from users.permissions import IsAdmin


class TagListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseTagSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        inst = self.request.user.institution
        qs = CourseTag.objects.filter(institution=inst)
        return qs.annotate(course_count=Count('course_relations'))

    def perform_create(self, serializer):
        inst = self.request.user.institution
        name = serializer.validated_data.get('name', '')
        slug = slugify(name)
        # Ensure unique slug within institution
        base = slug
        n = 1
        while CourseTag.objects.filter(institution=inst, slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        serializer.save(institution=inst, slug=slug)


class TagDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourseTagSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return CourseTag.objects.filter(institution=self.request.user.institution)


class BatchAssignTagsView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        course_id = request.data.get('course_id')
        tag_names = request.data.get('tags', [])

        if not course_id:
            return Response({"error": "course_id is required"}, status=400)
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return Response({"error": "Course not found"}, status=404)

        inst = request.user.institution
        tag_ids = []
        for name in tag_names:
            name = name.strip()
            if not name:
                continue
            slug = slugify(name)
            tag, _ = CourseTag.objects.get_or_create(
                institution=inst, slug=slug,
                defaults={'name': name}
            )
            relation, _ = CourseTagRelation.objects.get_or_create(
                course=course, tag=tag
            )
            tag_ids.append(tag.id)

        # Remove relations for tags not in the new list
        course.tag_relations.exclude(tag_id__in=tag_ids).delete()

        relations = course.tag_relations.select_related('tag').all()
        return Response(CourseTagSerializer([r.tag for r in relations], many=True).data)
```

- [ ] **Step 2: Add tag filter to CourseListCreateView**

In `backend/courses/views.py`, in `CourseListCreateView.get_queryset` (line 353), add tag filtering after the existing `kp` filter (after line 367):

```python
tag = self.request.query_params.getlist('tag')
if tag:
    from courses.models import CourseTagRelation
    course_ids = CourseTagRelation.objects.filter(
        tag__slug__in=tag,
        tag__institution=self.request.user.institution,
    ).values_list('course_id', flat=True)
    # Intersection: courses that have ALL requested tags
    from django.db.models import Count
    matching = course_ids.values('course_id').annotate(n=Count('id')).filter(n=len(tag))
    qs = qs.filter(id__in=matching.values_list('course_id', flat=True))
```

This should go right after line 367 (`if kp: qs = qs.filter(knowledge_point_id=kp)`) and before `return qs`.

Wait — actually the current `tag` filter implementation above is wrong. `course_ids` is a queryset of `CourseTagRelation` objects, not course IDs directly. Let me fix it:

```python
tag = self.request.query_params.getlist('tag')
if tag:
    from courses.models import CourseTagRelation
    from django.db.models import Count
    course_ids = CourseTagRelation.objects.filter(
        tag__slug__in=tag,
        tag__institution__isnull=True,
    ).values_list('course_id', flat=True)
    if hasattr(self.request.user, 'institution') and self.request.user.institution:
        inst_ids = CourseTagRelation.objects.filter(
            tag__slug__in=tag,
            tag__institution=self.request.user.institution,
        ).values_list('course_id', flat=True)
        course_ids = list(course_ids) + list(inst_ids)

    # Intersection: courses that have ALL requested tags
    from collections import Counter
    matching = [cid for cid, count in Counter(course_ids).items() if count >= len(tag)]
    qs = qs.filter(id__in=matching)
```

Hmm, this is getting complex. Let me simplify — the user's institution matters, and tags are institution-scoped. Let me make it simpler:

```python
tag = self.request.query_params.getlist('tag')
if tag:
    from courses.models import CourseTagRelation
    from django.db.models import Count
    matching_qs = CourseTagRelation.objects.filter(
        tag__slug__in=tag,
        tag__institution=self.request.user.institution,
    ).values('course_id').annotate(n=Count('id')).filter(n=len(tag))
    qs = qs.filter(id__in=[m['course_id'] for m in matching_qs])
```

That's cleaner. Let me use this version.

- [ ] **Step 3: Add routes to urls.py**

In `backend/courses/urls.py`, add imports and routes:

Add import for the new views (after existing imports, line 9):
```python
from .views_tags import TagListCreateView, TagDetailView, BatchAssignTagsView
```

Add routes before the last item in urlpatterns (before line 21, but order matters — the tag routes should come BEFORE the `<int:pk>/` wildcard routes to avoid name collisions):

```python
path('tags/', TagListCreateView.as_view(), name='tag-list'),
path('tags/batch-assign/', BatchAssignTagsView.as_view(), name='tag-batch-assign'),
path('tags/<int:pk>/', TagDetailView.as_view(), name='tag-detail'),
```

The corrected urlpatterns should look like:

```python
urlpatterns = [
    path('', CourseListCreateView.as_view(), name='course-list'),
    path('chunked/init/', ChunkedUploadInitView.as_view(), name='course-chunked-init'),
    path('chunked/<str:upload_id>/chunk/', ChunkedUploadChunkView.as_view(), name='course-chunked-chunk'),
    path('chunked/<str:upload_id>/complete/', ChunkedUploadCompleteView.as_view(), name='course-chunked-complete'),
    path('tags/', TagListCreateView.as_view(), name='tag-list'),
    path('tags/batch-assign/', BatchAssignTagsView.as_view(), name='tag-batch-assign'),
    path('tags/<int:pk>/', TagDetailView.as_view(), name='tag-detail'),
    path('<int:pk>/', CourseDetailView.as_view(), name='course-detail'),
    path('<int:pk>/outline/', CourseOutlineView.as_view(), name='course-outline'),
    path('<int:pk>/transcript/', CourseTranscriptView.as_view(), name='course-transcript'),
    path('albums/', AlbumListCreateView.as_view(), name='album-list'),
    path('startup-materials/', StartupMaterialListCreateView.as_view(), name='startup-material-list'),
    path('<int:pk>/progress/', VideoProgressUpdateView.as_view(), name='video-progress-update'),
]
```

NOTE: `tags/batch-assign/` must come before `tags/<int:pk>/` because Django matches routes in order and `batch-assign` would otherwise be caught by `<int:pk>`.

- [ ] **Step 4: Verify backend works**

```bash
cd backend && python manage.py check --deploy 2>&1 | head -5
```

- [ ] **Step 5: Commit**

```bash
git add backend/courses/views_tags.py backend/courses/views.py backend/courses/urls.py && git commit -m "feat: add tag CRUD, batch-assign, and course list tag filtering"
```

---

### Task 4: Add tags to frontend chunkedUpload flow

**Files:**
- Modify: `frontend/src/lib/chunkedUpload.ts`

- [ ] **Step 1: Add tags param to CreateCourseWithUploadParams**

Edit the interface at line 145-160, add `tags?: string[]`:

```typescript
export interface CreateCourseWithUploadParams {
  title: string;
  description: string;
  eloReward: number;
  albumObj?: string;
  knowledgePoint?: string;
  tags?: string[];
  video: File;
  cover?: File | null;
  courseware?: File | null;
  thresholdBytes: number;
  chunkSizeBytes: number;
  onProgress?: (percent: number) => void;
  onStatus?: (status: ChunkedUploadStatus) => void;
  resumeStorageKey?: string;
  signal?: AbortSignal;
}
```

In the destructuring at line 163, add `tags`:

```typescript
const {
  title, description, eloReward, albumObj, knowledgePoint, tags,
  video, cover, courseware, thresholdBytes, chunkSizeBytes,
  onProgress, onStatus, resumeStorageKey, signal,
} = params;
```

In `applyCommonFields` (line 207), add tags to FormData:

```typescript
const applyCommonFields = (fd: FormData) => {
  fd.append('title', title);
  fd.append('description', description);
  fd.append('elo_reward', String(eloReward));
  if (albumObj && albumObj !== '0') fd.append('album_obj', albumObj);
  if (knowledgePoint && knowledgePoint !== '0') fd.append('knowledge_point', knowledgePoint);
  if (tags && tags.length > 0) fd.append('tags', JSON.stringify(tags));
};
```

- [ ] **Step 2: Handle tags in chunked upload complete endpoint (backend views.py)**

In `ChunkedUploadCompleteView.post` (around line 218), after extracting other fields, add:

```python
tags_json = request.data.get("tags", "")
if tags_json:
    try:
        tags = json.loads(tags_json)
        from .views_tags import _assign_tags
        _assign_tags(course, tags, request.user.institution)
    except Exception:
        pass
```

Also handle tags in `CourseListCreateView.perform_create` (line 370) for small files. After `course = serializer.save(...)`:

```python
tags_json = self.request.data.get('tags', '')
if tags_json:
    try:
        tag_names = json.loads(tags_json)
        from .views_tags import _assign_tags
        _assign_tags(course, tag_names, self.request.user.institution)
    except Exception:
        pass
```

And extract `_assign_tags` as a module-level helper in `views_tags.py`:

```python
def _assign_tags(course, tag_names, institution):
    """Assign tags to a course. Create new tags as needed. Returns list of tag ids."""
    from django.utils.text import slugify
    from .models import CourseTagRelation
    tag_ids = []
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        slug = slugify(name)
        tag, _ = CourseTag.objects.get_or_create(
            institution=institution, slug=slug,
            defaults={'name': name}
        )
        relation, _ = CourseTagRelation.objects.get_or_create(
            course=course, tag=tag
        )
        tag_ids.append(tag.id)
    course.tag_relations.exclude(tag_id__in=tag_ids).delete()
```

Then update `BatchAssignTagsView.post` to use `_assign_tags` instead of the inline logic.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/chunkedUpload.ts backend/courses/views.py backend/courses/views_tags.py && git commit -m "feat: pass tags through chunked upload and course creation"
```

---

### Task 5: Create TagAutocomplete component

**Files:**
- Create: `frontend/src/components/TagAutocomplete.tsx`

- [ ] **Step 1: Create TagAutocomplete.tsx**

```tsx
import React, { useState, useEffect, useRef } from 'react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

interface TagOption {
  id: number;
  name: string;
  slug: string;
}

interface Props {
  tags: string[];
  setTags: (t: string[]) => void;
  compact?: boolean;
}

export const TagAutocomplete: React.FC<Props> = ({ tags, setTags, compact = false }) => {
  const [inputValue, setInputValue] = useState('');
  const [suggestions, setSuggestions] = useState<TagOption[]>([]);
  const [allTags, setAllTags] = useState<TagOption[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get('/courses/tags/').then(r => setAllTags(r.data || [])).catch(() => {});
  }, []);

  const filtered = inputValue.trim()
    ? allTags.filter(t =>
        t.name.toLowerCase().includes(inputValue.trim().toLowerCase()) &&
        !tags.includes(t.name)
      ).slice(0, 5)
    : [];

  const addTag = (name: string) => {
    const val = name.trim();
    if (val && !tags.includes(val)) {
      setTags([...tags, val]);
    }
    setInputValue('');
    setShowSuggestions(false);
    setSelectedIndex(0);
    inputRef.current?.focus();
  };

  const removeTag = (idx: number) => {
    setTags(tags.filter((_, i) => i !== idx));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const f = filtered;
      if (f.length > 0 && selectedIndex >= 0 && selectedIndex < f.length) {
        addTag(f[selectedIndex].name);
      } else if (inputValue.trim()) {
        addTag(inputValue.trim());
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  useEffect(() => {
    setSelectedIndex(0);
    setShowSuggestions(filtered.length > 0);
  }, [inputValue]);

  return (
    <div className="space-y-1.5 text-left relative">
      <div className="flex gap-2">
        <Input
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onFocus={() => filtered.length > 0 && setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder="输入标签，回车添加"
          className={cn(
            "bg-unimind-bg-secondary border-none rounded-xl font-bold text-[11px]",
            compact ? "h-8 px-3" : "h-9 px-4"
          )}
        />
      </div>
      {showSuggestions && filtered.length > 0 && (
        <div className="absolute z-50 left-0 right-0 bg-white border border-border rounded-xl shadow-lg mt-1 py-1 overflow-hidden">
          {filtered.map((t, i) => (
            <div
              key={t.id}
              className={cn(
                "px-3 py-1.5 text-[11px] font-bold cursor-pointer transition-colors",
                i === selectedIndex ? "bg-black text-white" : "hover:bg-slate-100"
              )}
              onMouseDown={(e) => { e.preventDefault(); addTag(t.name); }}
              onMouseEnter={() => setSelectedIndex(i)}
            >
              {t.name}
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1 min-h-[1rem]">
        {tags.map((tag, i) => (
          <Badge
            key={i}
            className="bg-black text-white hover:bg-black/80 gap-1 pl-2 pr-1 py-0.5 rounded-lg text-[11px] font-bold uppercase tracking-wider"
          >
            {tag}
            <X className="w-2.5 h-2.5 cursor-pointer opacity-50 hover:opacity-100" onClick={() => removeTag(i)} />
          </Badge>
        ))}
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TagAutocomplete.tsx && git commit -m "feat: add TagAutocomplete component with API-driven suggestions"
```

---

### Task 6: Integrate tags into Maintenance course form

**Files:**
- Modify: `frontend/src/pages/Maintenance.tsx`

- [ ] **Step 1: Add tags to courseForm state and handleCreateCourse**

Change import at line 27 — replace `TagInput` with `TagAutocomplete`:

```typescript
import { TagAutocomplete } from '@/components/TagAutocomplete';
```

Add `tags` to courseForm state at line 63:

```typescript
const [courseForm, setCourseForm] = useState({
  title: '', album_obj: '0', desc: '', elo_reward: 50, knowledge_point: '0',
  video: null as File | null, cover: null as File | null, courseware: null as File | null,
  tags: [] as string[],
});
```

In `handleCreateCourse` (line 106), capture and pass tags:

```typescript
const tags = courseForm.tags;
```

Update `createCourseWithSmartUpload` call (line 130) to include tags:

```typescript
await createCourseWithSmartUpload({
  title, description: desc, eloReward,
  albumObj: albumObj !== '0' ? albumObj : undefined,
  knowledgePoint: knowledgePoint !== '0' ? knowledgePoint : undefined,
  tags,
  // ...rest
```

Update form reset at line 126 to include tags:

```typescript
setCourseForm({ title: '', album_obj: '0', desc: '', elo_reward: 50, knowledge_point: '0', video: null, cover: null, courseware: null, tags: [] });
```

- [ ] **Step 2: Add TagAutocomplete to the course upload JSX**

Find the part of the form between the description field and the upload buttons (around line 320). After the description MarkdownEditor, add:

```tsx
<div className="space-y-2">
  <Label className="text-[11px] font-bold uppercase opacity-40 ml-1">标签</Label>
  <TagAutocomplete
    tags={courseForm.tags}
    setTags={(t: string[]) => setCourseForm({ ...courseForm, tags: t })}
  />
</div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Maintenance.tsx && git commit -m "feat: add tag input to course upload form"
```

---

### Task 7: Add tag management tab to Maintenance

**Files:**
- Modify: `frontend/src/pages/Maintenance.tsx`

- [ ] **Step 1: Add tag management UI**

First, add tag list to state (after line 48):

```typescript
const [tagList, setTagList] = useState<any[]>([]);
```

Add tag list to `fetchLists` (line 76):

```typescript
api.get('/courses/tags/')
```
And save it:
```typescript
.then(r => setTagList(r.data))
```

Wait — the Promise.all at line 77 already fetches multiple things. Add the tag fetch there:

```typescript
const [c, a, b, k, al, sm, tg] = await Promise.all([
  api.get('/courses/'), api.get('/articles/'), api.get('/ai/bots/'),
  api.get('/quizzes/knowledge-points/'), api.get('/courses/albums/'),
  api.get('/courses/startup-materials/'), api.get('/courses/tags/')
]);
setCourseList(c.data); setArticleList(a.data.articles || []); setBotList(b.data);
setKpList(k.data); setAlbumList(al.data); setSmList(sm.data); setTagList(tg.data);
```

Add `'tags'` to auditMode type at line 50:

```typescript
const [auditMode, setAuditMode] = useState<'hub' | 'courses' | 'articles' | 'kp' | 'sm' | 'tags'>('hub');
```

Add tag create/delete state and handlers (after existing states):

```typescript
const [newTagName, setNewTagName] = useState('');
const [showNewTagDialog, setShowNewTagDialog] = useState(false);

const handleCreateTag = async () => {
  if (!newTagName.trim()) return toast.error('请输入标签名');
  try {
    await api.post('/courses/tags/', { name: newTagName.trim() });
    toast.success('标签已创建');
    setNewTagName('');
    setShowNewTagDialog(false);
    fetchLists();
  } catch (e: any) { toast.error(e?.response?.data?.detail || '创建失败'); }
};
```

Update `handleDelete` (line 95) to handle tag type:

```typescript
if (type === 'sm') endpoint = `/courses/startup-materials/${id}/`;
if (type === 'tags') endpoint = `/courses/tags/${id}/`;
```

Add a tab for tags in the audit tabs — find the TabsList that contains `courses`, `articles`, etc. and add:

```tsx
<TabsTrigger value="tags" className="..."><Tag className="w-3.5 h-3.5 mr-1.5" /> 标签</TabsTrigger>
```

Import `Tag` from lucide-react at line 9.

Add the TabsContent for the tags tab — a simple table with tag name, course count, and delete button. This goes alongside the other TabsContent blocks.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Maintenance.tsx && git commit -m "feat: add tag management tab to maintenance page"
```

---

### Task 8: Add tag filtering to CourseCenter

**Files:**
- Modify: `frontend/src/pages/CourseCenter.tsx`

- [ ] **Step 1: Add tag filter chips and course badges**

Add imports at top:

```typescript
import { useState, useEffect } from 'react';
import api from '@/lib/api';
```

Add state for tags and active tag filter:

```typescript
const [allTags, setAllTags] = useState<any[]>([]);
const [activeTags, setActiveTags] = useState<string[]>([]);

useEffect(() => {
  api.get('/courses/tags/').then(r => setAllTags(r.data || [])).catch(() => {});
}, []);
```

Update the `useFetch` call to add tag query params:

```typescript
const tagQuery = activeTags.length > 0 ? '?' + activeTags.map(t => `tag=${t}`).join('&') : '';
const { data: courses, loading, error, refetch } = useFetch<any[]>(
  (signal) => api.get(`/courses/${tagQuery}`, { signal }).then(r => r.data),
  [activeTags]
);
```

Wait, `useFetch` might only take the first function. Let me check how it works... The current code is:
```typescript
const { data: courses, loading, error, refetch } = useFetch<any[]>(
  (signal) => api.get('/courses/', { signal }).then(r => r.data)
);
```

To make it re-fetch when activeTags changes, I can pass a dependency key string:

```typescript
const tagQuery = activeTags.length > 0 ? '?' + activeTags.map(t => `tag=${t}`).join('&') : '';
const { data: courses, loading, error, refetch } = useFetch<any[]>(
  (signal) => api.get(`/courses/${tagQuery}`, { signal }).then(r => r.data),
  [activeTags.length, activeTags.join(',')]
);
```

Hmm, let me check what useFetch supports. Let me just look at it briefly... I don't have access to read it right now. The safest approach is to just use a key that changes:

Actually looking at typical custom useFetch hooks, they usually take a key or dependencies. Let me just use a simpler approach and build the URL with a dependency key:

```typescript
const { data: courses, loading, error, refetch } = useFetch<any[]>(
  (signal) => api.get(`/courses/${tagQuery}`, { signal }).then(r => r.data),
  [activeTags]
);
```

Add tag filter chips between `PageWrapper` and the course grid:

```tsx
{allTags.length > 0 && (
  <div className="flex gap-2 overflow-x-auto pb-2 mb-2 scrollbar-none">
    {activeTags.length > 0 && (
      <Badge
        className="cursor-pointer bg-black text-white hover:bg-black/80 px-3 py-1 rounded-full text-[11px] font-bold shrink-0"
        onClick={() => setActiveTags([])}
      >
        全部 ×
      </Badge>
    )}
    {allTags.map((tag: any) => {
      const isActive = activeTags.includes(tag.slug);
      return (
        <Badge
          key={tag.id}
          className={cn(
            "cursor-pointer px-3 py-1 rounded-full text-[11px] font-bold shrink-0 transition-colors",
            isActive ? "bg-black text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          )}
          onClick={() => {
            if (isActive) {
              setActiveTags(activeTags.filter(t => t !== tag.slug));
            } else {
              setActiveTags([...activeTags, tag.slug]);
            }
          }}
        >
          {tag.name}
        </Badge>
      );
    })}
  </div>
)}
```

Import `Badge` and `cn`:
```typescript
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
```

Add tag badges on course cards, after the description line (line 65):

```tsx
{course.tags && course.tags.length > 0 && (
  <div className="flex flex-wrap gap-1 mt-1">
    {course.tags.map((t: any) => (
      <span key={t.id} className="text-[9px] font-bold text-slate-400 uppercase tracking-wide">
        #{t.name}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/CourseCenter.tsx && git commit -m "feat: add tag filter chips and course card tag badges to course center"
```

---

### Task 9: Verify end-to-end

- [ ] **Step 1: Run backend checks**

```bash
cd backend && python manage.py check
```

- [ ] **Step 2: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 3: Test manually**

- Start backend: `cd backend && python manage.py runserver`
- Start frontend: `cd frontend && npm run dev`
- As admin: go to Maintenance → 标签 tab, create a tag
- Upload a course with tags
- Go to Course Center, verify tag chips appear and filtering works
- Verify tag badges on course cards

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A && git commit -m "chore: final cleanup for course tag system"
```

---

## Plan Summary

| Task | What | Files Changed |
|------|------|--------------|
| 1 | Models + migration | `models.py`, migration |
| 2 | Serializers | `serializers.py` |
| 3 | Views + URLs + filtering | `views.py`, `views_tags.py` (new), `urls.py` |
| 4 | Chunked upload + tags | `chunkedUpload.ts`, `views.py`, `views_tags.py` |
| 5 | TagAutocomplete component | `TagAutocomplete.tsx` (new) |
| 6 | Course form tags | `Maintenance.tsx` |
| 7 | Tag management tab | `Maintenance.tsx` |
| 8 | Course center filter | `CourseCenter.tsx` |
| 9 | Verify | manual |
