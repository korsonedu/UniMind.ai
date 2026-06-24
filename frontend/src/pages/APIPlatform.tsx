/**
 * API 开放平台 — 企业开发者门户
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Code,
  Key,
  Copy,
  Trash,
  BookOpen,
  Plus,
  Spinner,
  ChartBar,
  Gauge,
  Clock,
  CheckCircle,
  X,
} from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

interface ApiKey {
  id: number;
  name: string;
  key_id: string;
  scopes: string[];
  rate_limit: number;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

const SCOPE_LABELS: Record<string, string> = {
  'read:questions': '读取题库',
  'read:analytics': '读取分析',
};

function maskSecret(keyId: string): string {
  if (keyId.length <= 12) return keyId;
  return keyId.slice(0, 8) + '…' + keyId.slice(-4);
}

export function APIPlatform() {
  const [tab, setTab] = useState('keys');

  return (
    <PageWrapper title="API 开放平台" subtitle="通过 API 接入 UniMind 数据和能力">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="keys">
            <Key className="mr-1.5 h-4 w-4" />
            API 密钥
          </TabsTrigger>
          <TabsTrigger value="docs">
            <BookOpen className="mr-1.5 h-4 w-4" />
            API 文档
          </TabsTrigger>
          <TabsTrigger value="usage">
            <Gauge className="mr-1.5 h-4 w-4" />
            用量概览
          </TabsTrigger>
        </TabsList>
        <TabsContent value="keys">
          <ApiKeysTab />
        </TabsContent>
        <TabsContent value="docs">
          <ApiDocsTab />
        </TabsContent>
        <TabsContent value="usage">
          <UsageTab />
        </TabsContent>
      </Tabs>
    </PageWrapper>
  );
}

/* ──────────── API Keys Tab ──────────── */

function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const { confirm, Dialog: ConfirmDialog } = useConfirm();

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/users/institution/me/api-keys/');
      setKeys(Array.isArray(data) ? data : []);
    } catch {
      toast.error('加载 API 密钥失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    const scopes = form.getAll('scopes') as string[];
    if (scopes.length === 0) {
      toast.error('请至少选择一个权限范围');
      setSubmitting(false);
      return;
    }
    const payload = {
      name: (form.get('name') as string).trim(),
      scopes,
      rate_limit: parseInt(form.get('rate_limit') as string) || 1000,
    };
    try {
      const { data } = await api.post('/users/institution/me/api-keys/', payload);
      setNewSecret(data.secret);
      setShowCreate(false);
      await fetchKeys();
      toast.success('API 密钥已创建');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '创建失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggle(key: ApiKey) {
    try {
      await api.put(`/users/institution/me/api-keys/${key.id}/`, { is_active: !key.is_active });
      await fetchKeys();
      toast.success(key.is_active ? '密钥已停用' : '密钥已启用');
    } catch {
      toast.error('操作失败');
    }
  }

  async function handleDelete(key: ApiKey) {
    if (!(await confirm(`确定删除密钥「${key.name}」？使用该密钥的集成将立即失效。`))) return;
    try {
      await api.delete(`/users/institution/me/api-keys/${key.id}/`);
      await fetchKeys();
      toast.success('密钥已删除');
    } catch {
      toast.error('删除失败');
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).then(
      () => toast.success('已复制到剪贴板'),
      () => toast.error('复制失败')
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="animate-spin h-6 w-6 text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Secret reveal alert */}
      {newSecret && (
        <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Key className="h-5 w-5 text-yellow-700" />
            <span className="font-semibold text-yellow-800">API 密钥已创建</span>
          </div>
          <p className="text-sm text-yellow-700">
            请立即保存此密钥，关闭后将无法再次查看：
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-yellow-100 border border-yellow-300 rounded px-3 py-2 text-sm font-mono break-all text-yellow-900">
              {newSecret}
            </code>
            <Button variant="outline" size="sm" onClick={() => copyToClipboard(newSecret)}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setNewSecret(null)}>
            <X className="mr-1 h-3 w-3" />
            关闭
          </Button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          共 {keys.length} 个密钥
        </p>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="mr-1 h-4 w-4" />
          创建 API 密钥
        </Button>
      </div>

      {keys.length === 0 ? (
        <div className="text-center py-20 space-y-3">
          <Key className="mx-auto h-12 w-12 text-muted-foreground/30" />
          <p className="text-muted-foreground">暂未创建 API 密钥</p>
          <Button variant="outline" onClick={() => setShowCreate(true)}>
            <Plus className="mr-1 h-4 w-4" />
            创建第一个密钥
          </Button>
        </div>
      ) : (
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/50 border-b border-border">
                  <th className="text-left px-4 py-3 font-bold text-muted-foreground">名称</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">Key ID</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">权限范围</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">频率限制</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">状态</th>
                  <th className="text-left px-3 py-3 font-bold text-muted-foreground">最后使用</th>
                  <th className="text-right px-4 py-3 font-bold text-muted-foreground">操作</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2.5 font-medium">{key.name}</td>
                    <td className="px-3 py-2.5">
                      <button
                        className="font-mono text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                        onClick={() => copyToClipboard(key.key_id)}
                        title="点击复制"
                      >
                        {maskSecret(key.key_id)}
                      </button>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {key.scopes.map((scope) => (
                          <Badge key={scope} variant="outline" className="text-xs">
                            {SCOPE_LABELS[scope] || scope}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground tabular-nums">
                      {key.rate_limit} 次/分钟
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={key.is_active}
                          onCheckedChange={() => handleToggle(key)}
                        />
                        <span className={cn('text-xs', key.is_active ? 'text-green-600' : 'text-muted-foreground')}>
                          {key.is_active ? '启用' : '停用'}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground text-xs">
                      {key.last_used_at
                        ? new Date(key.last_used_at).toLocaleDateString('zh-CN')
                        : '从未使用'}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <Button variant="ghost" size="sm" onClick={() => handleDelete(key)}>
                        <Trash className="h-4 w-4 text-destructive" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {ConfirmDialog}
      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>创建 API 密钥</DialogTitle>
            <DialogDescription>创建一个新的 API 密钥用于外部系统集成。</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 mt-2">
            <div>
              <Label htmlFor="ak-name">密钥名称 *</Label>
              <Input id="ak-name" name="name" required placeholder="如：生产环境集成" />
            </div>
            <div>
              <Label className="mb-2 block">权限范围 *</Label>
              <div className="space-y-2 border rounded-lg p-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <Checkbox name="scopes" value="read:questions" />
                  <div>
                    <p className="text-sm font-medium">读取题库</p>
                    <p className="text-xs text-muted-foreground">允许通过 API 查询题库内容</p>
                  </div>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <Checkbox name="scopes" value="read:analytics" />
                  <div>
                    <p className="text-sm font-medium">读取分析</p>
                    <p className="text-xs text-muted-foreground">允许访问分析数据接口</p>
                  </div>
                </label>
              </div>
            </div>
            <div>
              <Label htmlFor="ak-rate">频率限制（次/分钟）</Label>
              <Input id="ak-rate" name="rate_limit" type="number" min="1" defaultValue={1000} />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? <Spinner className="animate-spin mr-1 h-4 w-4" /> : <Plus className="mr-1 h-4 w-4" />}
              创建密钥
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ──────────── API Docs Tab ──────────── */

function ApiDocsTab() {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  function copySnippet(text: string, id: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      toast.success('已复制');
      setTimeout(() => setCopiedId(null), 2000);
    }).catch(() => toast.error('复制失败'));
  }

  const questionsCurl = `curl -X GET \\
  "https://api.unimind.ai/v1/questions/?subject=math&page=1" \\
  -H "Authorization: Bearer YOUR_KEY_ID:YOUR_SIGNATURE" \\
  -H "X-UniMind-Date: $(date -u +%Y%m%dT%H%M%SZ)"`;

  const analyticsCurl = `curl -X GET \\
  "https://api.unimind.ai/v1/analytics/overview/" \\
  -H "Authorization: Bearer YOUR_KEY_ID:YOUR_SIGNATURE" \\
  -H "X-UniMind-Date: $(date -u +%Y%m%dT%H%M%SZ)"`;

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Quick Start */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-primary" />
            快速开始
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            UniMind API 使用 HMAC 签名认证。每个请求需要提供 <code className="bg-muted px-1.5 py-0.5 rounded text-xs">key_id:signature</code> 格式的 Bearer Token。
          </p>

          <div>
            <h4 className="font-semibold mb-2">签名算法</h4>
            <ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
              <li>拼接请求方法 + 路径 + 时间戳</li>
              <li>使用 API Secret 进行 HMAC-SHA256 签名</li>
              <li>将签名结果 Base64 编码</li>
              <li>在 Authorization header 中传 <code className="bg-muted px-1.5 py-0.5 rounded text-xs">Bearer key_id:signature</code></li>
            </ol>
          </div>

          <div>
            <h4 className="font-semibold mb-2">Python 示例</h4>
            <div className="relative bg-zinc-950 text-zinc-50 rounded-lg p-4 overflow-x-auto">
              <button
                className="absolute top-2 right-2 p-1.5 rounded hover:bg-zinc-800 transition-colors"
                onClick={() => copySnippet(`import hmac, hashlib, base64, time, requests

key_id = "your_key_id"
secret = "your_secret"
method = "GET"
path = "/v1/questions/"
timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

signing_string = f"{method}\\n{path}\\n{timestamp}"
signature = base64.b64encode(
    hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).digest()
).decode()

headers = {
    "Authorization": f"Bearer {key_id}:{signature}",
    "X-UniMind-Date": timestamp,
}
resp = requests.get("https://api.unimind.ai/v1/questions/", headers=headers)
print(resp.json())`, 'python')}
              >
                <Copy className={cn('h-3.5 w-3.5', copiedId === 'python' ? 'text-green-400' : 'text-zinc-400')} />
              </button>
              <pre className="text-xs leading-relaxed"><code>{`import hmac, hashlib, base64, time, requests

key_id = "your_key_id"
secret = "your_secret"
method = "GET"
path = "/v1/questions/"
timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

signing_string = f"{method}\\n{path}\\n{timestamp}"
signature = base64.b64encode(
    hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).digest()
).decode()

headers = {
    "Authorization": f"Bearer {key_id}:{signature}",
    "X-UniMind-Date": timestamp,
}
resp = requests.get("https://api.unimind.ai/v1/questions/", headers=headers)
print(resp.json())`}</code></pre>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Endpoint Reference */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code className="h-5 w-5 text-primary" />
            接口参考
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* GET /v1/questions/ */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="default" className="bg-blue-600 text-xs">GET</Badge>
              <code className="font-mono text-sm font-semibold">/v1/questions/</code>
              <Badge variant="outline" className="text-xs">read:questions</Badge>
            </div>
            <p className="text-sm text-muted-foreground mb-3">查询题库内容，支持按学科分页筛选。</p>
            <div className="relative bg-zinc-950 text-zinc-50 rounded-lg p-3 overflow-x-auto">
              <button
                className="absolute top-2 right-2 p-1.5 rounded hover:bg-zinc-800 transition-colors"
                onClick={() => copySnippet(questionsCurl, 'questions')}
              >
                <Copy className={cn('h-3.5 w-3.5', copiedId === 'questions' ? 'text-green-400' : 'text-zinc-400')} />
              </button>
              <pre className="text-xs leading-relaxed"><code>{questionsCurl}</code></pre>
            </div>
          </div>

          {/* GET /v1/analytics/overview/ */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="default" className="bg-blue-600 text-xs">GET</Badge>
              <code className="font-mono text-sm font-semibold">/v1/analytics/overview/</code>
              <Badge variant="outline" className="text-xs">read:analytics</Badge>
            </div>
            <p className="text-sm text-muted-foreground mb-3">获取机构关键分析指标概览。</p>
            <div className="relative bg-zinc-950 text-zinc-50 rounded-lg p-3 overflow-x-auto">
              <button
                className="absolute top-2 right-2 p-1.5 rounded hover:bg-zinc-800 transition-colors"
                onClick={() => copySnippet(analyticsCurl, 'analytics')}
              >
                <Copy className={cn('h-3.5 w-3.5', copiedId === 'analytics' ? 'text-green-400' : 'text-zinc-400')} />
              </button>
              <pre className="text-xs leading-relaxed"><code>{analyticsCurl}</code></pre>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ──────────── Usage Tab ──────────── */

function UsageTab() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.get('/users/institution/me/api-keys/')
      .then(({ data }) => {
        if (cancelled) return;
        setKeys(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (cancelled) return;
        toast.error('加载密钥列表失败');
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="animate-spin h-6 w-6 text-muted-foreground" />
      </div>
    );
  }

  const activeKeys = keys.filter((k) => k.is_active);
  const lastUsedDates = keys
    .map((k) => k.last_used_at)
    .filter(Boolean)
    .sort()
    .reverse();

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Key className="h-3.5 w-3.5" />
              活跃密钥
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{activeKeys.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Key className="h-3.5 w-3.5" />
              总密钥数
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{keys.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" />
              最近使用
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-bold">
              {lastUsedDates.length > 0
                ? new Date(lastUsedDates[0]!).toLocaleDateString('zh-CN')
                : '从未使用'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Coming soon */}
      <Card className="border-dashed">
        <CardContent className="py-8 text-center space-y-2">
          <ChartBar className="mx-auto h-8 w-8 text-muted-foreground/40" />
          <p className="text-muted-foreground text-sm">详细的请求计数和调用频率统计即将上线</p>
        </CardContent>
      </Card>
    </div>
  );
}
