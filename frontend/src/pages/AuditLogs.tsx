import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageWrapper } from '@/components/PageWrapper';
import api from '@/lib/api';
import { Shield, ChevronLeft, ChevronRight } from 'lucide-react';

interface AuditLog {
  id: number;
  operator: string;
  action: string;
  detail: string;
  created_at: string;
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/users/institution/me/audit-logs/?page=${page}`)
      .then(r => {
        setLogs(r.data.items || []);
        setTotal(r.data.total || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = Math.ceil(total / 20);

  const actionLabels: Record<string, string> = {
    'purchase_plan': '购买方案',
    'create_student': '创建学员',
    'delete_student': '删除学员',
    'update_student': '更新学员',
    'activate_institution': '激活机构',
    'deactivate_institution': '停用机构',
    'change_plan': '变更方案',
    'update_features': '更新功能',
    'regenerate_invite': '重置邀请链接',
  };

  return (
    <PageWrapper title="操作日志" subtitle="机构操作审计记录">
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Shield className="h-4 w-4" />
          <span>共 {total} 条记录</span>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">加载中...</div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">暂无操作记录</div>
        ) : (
          <div className="space-y-2">
            {logs.map(log => (
              <Card key={log.id} className="border-none shadow-sm rounded-2xl bg-white p-4 border border-black/[0.03]">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-foreground">{log.operator}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-muted-foreground font-medium">
                        {actionLabels[log.action] || log.action}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{log.detail}</p>
                  </div>
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                    {new Date(log.created_at).toLocaleString('zh-CN')}
                  </span>
                </div>
              </Card>
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-xl"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-xs text-muted-foreground">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="rounded-xl"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
