/**
 * 内容市场 — 机构间题库与课程共享
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Storefront,
  MagnifyingGlass,
  Download,
  Plus,
  Pencil,
  Trash,
  Spinner,
  CheckCircle,
  Package,
  Star,
} from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';
import { useAuthStore } from '@/store/useAuthStore';

interface Listing {
  id: number;
  title: string;
  description: string;
  publisher: number | null;
  publisher_name: string;
  subject: string;
  content_type: string;
  grade: string;
  license_type: string;
  price_cents: number;
  downloads: number;
  rating: number;
  status: string;
  content_ids: number[];
  created_at: string;
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  question: '题库',
  course: '课程',
  template: '出题模板',
};

const LICENSE_LABELS: Record<string, string> = {
  free: '免费',
  buyout: '买断',
  subscription: '订阅',
};

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  published: '已上架',
  unpublished: '已下架',
};

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  draft: 'secondary',
  published: 'default',
  unpublished: 'outline',
};

function formatPrice(cents: number): string {
  if (cents === 0) return '免费';
  return `¥${(cents / 100).toFixed(2)}`;
}

export function Marketplace() {
  const { user } = useAuthStore();
  const isSuperAdmin = user?.role === 'admin' && !user?.institution;
  const [tab, setTab] = useState('browse');

  if (!isSuperAdmin) {
    return (
      <PageWrapper title="内容市场" subtitle="官方题库与课程共享">
        <BrowseTab />
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title="内容市场" subtitle="官方内容管理">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="browse">
            <Storefront className="mr-1.5 h-4 w-4" />
            发现内容
          </TabsTrigger>
          <TabsTrigger value="listings">
            <Package className="mr-1.5 h-4 w-4" />
            我的上架
          </TabsTrigger>
        </TabsList>
        <TabsContent value="browse">
          <BrowseTab />
        </TabsContent>
        <TabsContent value="listings">
          <MyListingsTab />
        </TabsContent>
      </Tabs>
    </PageWrapper>
  );
}

/* ──────────── Browse Tab ──────────── */

function BrowseTab() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [subject, setSubject] = useState('');
  const [contentType, setContentType] = useState('');
  const [licenseType, setLicenseType] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<Listing | null>(null);
  const [fetchingDetail, setFetchingDetail] = useState(false);

  const fetchListings = useCallback(async (pageNum = 1) => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page: pageNum, page_size: 12 };
      if (search) params.search = search;
      if (subject) params.subject = subject;
      if (contentType) params.content_type = contentType;
      if (licenseType) params.license_type = licenseType;
      const { data } = await api.get('/quizzes/marketplace/', { params });
      setListings(Array.isArray(data.listings) ? data.listings : []);
      setTotal(data.total || 0);
    } catch {
      toast.error('加载内容列表失败');
    } finally {
      setLoading(false);
    }
  }, [search, subject, contentType, licenseType]);

  useEffect(() => {
    fetchListings(1);
    setPage(1);
  }, [fetchListings]);

  function handleSearch() {
    fetchListings(1);
    setPage(1);
  }

  async function openDetail(listing: Listing) {
    setFetchingDetail(true);
    try {
      const { data } = await api.get(`/quizzes/marketplace/${listing.id}/`);
      setDetail(data);
    } catch {
      toast.error('加载详情失败');
    } finally {
      setFetchingDetail(false);
    }
  }

  async function handlePurchase(listing: Listing) {
    try {
      const { data } = await api.post(`/quizzes/marketplace/${listing.id}/purchase/`);
      if (listing.license_type === 'free' || listing.price_cents === 0) {
        toast.success('下载成功，内容已添加至您的资产库');
      } else if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast.success('购买成功');
      }
    } catch {
      toast.error('操作失败，请稍后重试');
    }
  }

  const totalPages = Math.ceil(total / 12);

  return (
    <div className="space-y-4">
      {/* Search & Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索内容…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="pl-9"
          />
        </div>
        <Select value={contentType} onValueChange={setContentType}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="内容类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="question">题库</SelectItem>
            <SelectItem value="course">课程</SelectItem>
            <SelectItem value="template">出题模板</SelectItem>
          </SelectContent>
        </Select>
        <Select value={licenseType} onValueChange={setLicenseType}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="许可类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="free">免费</SelectItem>
            <SelectItem value="buyout">买断</SelectItem>
            <SelectItem value="subscription">订阅</SelectItem>
          </SelectContent>
        </Select>
        <Input
          placeholder="学科"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          className="w-28"
        />
        <Button variant="outline" size="sm" onClick={handleSearch}>
          <MagnifyingGlass className="mr-1 h-4 w-4" />
          搜索
        </Button>
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner className="animate-spin h-6 w-6 text-muted-foreground" />
        </div>
      ) : listings.length === 0 ? (
        <div className="text-center py-20 space-y-3">
          <Storefront className="mx-auto h-12 w-12 text-muted-foreground/30" />
          <p className="text-muted-foreground">暂无上架内容</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {listings.map((item) => (
              <Card
                key={item.id}
                className="p-4 hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => openDetail(item)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-sm line-clamp-2 flex-1">{item.title}</h3>
                </div>
                <p className="text-xs text-muted-foreground mb-3">{item.publisher_name}</p>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {item.publisher === null && (
                    <Badge variant="default" className="text-xs bg-blue-600">官方</Badge>
                  )}
                  {item.subject && (
                    <Badge variant="outline" className="text-xs">{item.subject}</Badge>
                  )}
                  <Badge variant="secondary" className="text-xs">
                    {CONTENT_TYPE_LABELS[item.content_type] || item.content_type}
                  </Badge>
                  {item.license_type === 'free' || item.price_cents === 0 ? (
                    <Badge variant="default" className="text-xs bg-green-600">免费</Badge>
                  ) : (
                    <Badge variant="default" className="text-xs">{formatPrice(item.price_cents)}</Badge>
                  )}
                </div>
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Download className="h-3.5 w-3.5" /> {item.downloads}
                  </span>
                  <span className="flex items-center gap-1">
                    <Star className="h-3.5 w-3.5" /> {item.rating != null ? item.rating.toFixed(1) : '—'}
                  </span>
                </div>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => { const next = page - 1; setPage(next); fetchListings(next); }}
              >
                上一页
              </Button>
              <span className="text-sm text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => { const next = page + 1; setPage(next); fetchListings(next); }}
              >
                下一页
              </Button>
            </div>
          )}
        </>
      )}

      {/* Detail Dialog */}
      <Dialog open={!!detail} onOpenChange={(v) => { if (!v) setDetail(null); }}>
        <DialogContent className="max-w-lg">
          {fetchingDetail ? (
            <div className="flex items-center justify-center py-12">
              <Spinner className="animate-spin h-6 w-6 text-muted-foreground" />
            </div>
          ) : detail ? (
            <>
              <DialogHeader>
                <DialogTitle>{detail.title}</DialogTitle>
                <DialogDescription>{detail.publisher_name}</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 mt-2">
                <p className="text-sm text-muted-foreground">{detail.description || '暂无描述'}</p>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-muted-foreground">内容类型</span>
                    <p className="font-medium">{CONTENT_TYPE_LABELS[detail.content_type] || detail.content_type}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">学科</span>
                    <p className="font-medium">{detail.subject || '—'}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">年级</span>
                    <p className="font-medium">{detail.grade || '—'}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">许可类型</span>
                    <p className="font-medium">{LICENSE_LABELS[detail.license_type] || detail.license_type}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">价格</span>
                    <p className="font-medium">{formatPrice(detail.price_cents)}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">下载次数</span>
                    <p className="font-medium">{detail.downloads}</p>
                  </div>
                </div>
                <Button className="w-full" onClick={() => handlePurchase(detail)}>
                  <Download className="mr-1.5 h-4 w-4" />
                  免费获取
                </Button>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ──────────── My Listings Tab ──────────── */

function MyListingsTab() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPublish, setShowPublish] = useState(false);
  const [editItem, setEditItem] = useState<Listing | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { confirm, Dialog: ConfirmDialog } = useConfirm();

  const fetchMyListings = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/quizzes/marketplace/manage/');
      setListings(Array.isArray(data) ? data : []);
    } catch {
      toast.error('加载我的上架列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMyListings();
  }, [fetchMyListings]);

  async function handlePublish(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    const payload: Record<string, unknown> = {
      title: (form.get('title') as string).trim(),
      description: (form.get('description') as string).trim(),
      content_type: form.get('content_type'),
      subject: (form.get('subject') as string).trim(),
      grade: (form.get('grade') as string).trim(),
      price_cents: parseInt(form.get('price_cents') as string) || 0,
      license_type: form.get('license_type'),
    };
    const contentIdsStr = (form.get('content_ids') as string).trim();
    if (contentIdsStr) {
      payload.content_ids = contentIdsStr.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n));
    }
    try {
      await api.post('/quizzes/marketplace/publish/', payload);
      setShowPublish(false);
      await fetchMyListings();
      toast.success('发布成功');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '发布失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEdit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editItem) return;
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    const payload: Record<string, unknown> = {
      title: (form.get('title') as string).trim(),
      description: (form.get('description') as string).trim(),
      content_type: form.get('content_type'),
      subject: (form.get('subject') as string).trim(),
      grade: (form.get('grade') as string).trim(),
      price_cents: parseInt(form.get('price_cents') as string) || 0,
      license_type: form.get('license_type'),
    };
    const contentIdsStr = (form.get('content_ids') as string).trim();
    if (contentIdsStr) {
      payload.content_ids = contentIdsStr.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n));
    }
    try {
      await api.put(`/quizzes/marketplace/manage/${editItem.id}/`, payload);
      setEditItem(null);
      await fetchMyListings();
      toast.success('更新成功');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '更新失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(item: Listing) {
    if (!(await confirm(`确定删除「${item.title}」？此操作不可撤销。`))) return;
    try {
      await api.delete(`/quizzes/marketplace/manage/${item.id}/`);
      await fetchMyListings();
      toast.success('已删除');
    } catch {
      toast.error('删除失败');
    }
  }

  async function handleStatusChange(item: Listing, newStatus: string) {
    try {
      await api.put(`/quizzes/marketplace/manage/${item.id}/`, { status: newStatus });
      await fetchMyListings();
      toast.success(`状态已更新为「${STATUS_LABELS[newStatus] || newStatus}」`);
    } catch {
      toast.error('状态更新失败');
    }
  }

  const publishForm = (item?: Listing) => (
    <form onSubmit={item ? handleEdit : handlePublish} className="space-y-4 mt-2">
      <div>
        <Label htmlFor="ml-title">标题 *</Label>
        <Input id="ml-title" name="title" required defaultValue={item?.title || ''} placeholder="内容标题" />
      </div>
      <div>
        <Label htmlFor="ml-desc">描述</Label>
        <Textarea id="ml-desc" name="description" defaultValue={item?.description || ''} placeholder="内容描述…" rows={3} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="ml-type">内容类型</Label>
          <Select name="content_type" defaultValue={item?.content_type || 'question'}>
            <SelectTrigger id="ml-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="question">题库</SelectItem>
              <SelectItem value="course">课程</SelectItem>
              <SelectItem value="template">出题模板</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="ml-subject">学科</Label>
          <Input id="ml-subject" name="subject" defaultValue={item?.subject || ''} placeholder="如：数学" />
        </div>
        <div>
          <Label htmlFor="ml-grade">年级</Label>
          <Input id="ml-grade" name="grade" defaultValue={item?.grade || ''} placeholder="如：高中一年级" />
        </div>
        <div>
          <Label htmlFor="ml-price">价格（分）</Label>
          <Input id="ml-price" name="price_cents" type="number" min="0" defaultValue={item?.price_cents || 0} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="ml-license">许可类型</Label>
          <Select name="license_type" defaultValue={item?.license_type || 'free'}>
            <SelectTrigger id="ml-license">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="free">免费</SelectItem>
              <SelectItem value="buyout">买断</SelectItem>
              <SelectItem value="subscription">订阅</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="ml-ids">内容 ID 列表</Label>
          <Input
            id="ml-ids"
            name="content_ids"
            defaultValue={item?.content_ids ? item.content_ids.join(', ') : ''}
            placeholder="1, 2, 3"
          />
          <p className="text-xs text-muted-foreground mt-1">输入要关联的题目/课程 ID，逗号分隔</p>
        </div>
      </div>
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? <Spinner className="animate-spin mr-1 h-4 w-4" /> : (item ? <CheckCircle className="mr-1 h-4 w-4" /> : <Plus className="mr-1 h-4 w-4" />)}
        {item ? '保存修改' : '发布内容'}
      </Button>
    </form>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="animate-spin h-6 w-6 text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          共 {listings.length} 条内容
        </p>
        <Button size="sm" onClick={() => setShowPublish(true)}>
          <Plus className="mr-1 h-4 w-4" />
          发布内容
        </Button>
      </div>

      {listings.length === 0 ? (
        <div className="text-center py-20 space-y-3">
          <Package className="mx-auto h-12 w-12 text-muted-foreground/30" />
          <p className="text-muted-foreground">暂未上架任何内容</p>
          <Button variant="outline" onClick={() => setShowPublish(true)}>
            <Plus className="mr-1 h-4 w-4" />
            发布第一条内容
          </Button>
        </div>
      ) : (
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/50 border-b border-border">
                  <th className="text-left px-4 py-3 font-bold text-muted-foreground">标题</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">状态</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">类型</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">下载</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">创建时间</th>
                  <th className="text-right px-4 py-3 font-bold text-muted-foreground">操作</th>
                </tr>
              </thead>
              <tbody>
                {listings.map((item) => (
                  <tr key={item.id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2.5 font-medium">{item.title}</td>
                    <td className="px-3 py-2.5">
                      <Select
                        value={item.status}
                        onValueChange={(v) => handleStatusChange(item, v)}
                      >
                        <SelectTrigger className="h-7 w-24 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="draft">草稿</SelectItem>
                          <SelectItem value="published">已上架</SelectItem>
                          <SelectItem value="unpublished">已下架</SelectItem>
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge variant="secondary" className="text-xs">
                        {CONTENT_TYPE_LABELS[item.content_type] || item.content_type}
                      </Badge>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground">{item.downloads}</td>
                    <td className="px-3 py-2.5 text-muted-foreground text-xs">
                      {new Date(item.created_at).toLocaleDateString('zh-CN')}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditItem(item)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleDelete(item)}>
                          <Trash className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Publish Dialog */}
      <Dialog open={showPublish} onOpenChange={setShowPublish}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>发布内容</DialogTitle>
            <DialogDescription>将题库、课程或出题模板上架到内容市场。</DialogDescription>
          </DialogHeader>
          {publishForm()}
        </DialogContent>
      </Dialog>

      {ConfirmDialog}
      {/* Edit Dialog */}
      <Dialog open={!!editItem} onOpenChange={(v) => { if (!v) setEditItem(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑内容</DialogTitle>
          </DialogHeader>
          {editItem && publishForm(editItem)}
        </DialogContent>
      </Dialog>
    </div>
  );
}
