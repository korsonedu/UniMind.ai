import React, { useState, useCallback, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Bell, Envelope, Spinner } from '@phosphor-icons/react';
import api from '@/lib/api';
import { toast } from 'sonner';

export const NotificationConfigSection: React.FC = () => {
  const [config, setConfig] = useState({
    enabled: false,
    channel: 'email' as 'email' | 'feishu',
    due_threshold: 5,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await api.get('/users/institution/me/notification-config/');
      setConfig({
        enabled: res.data.enabled ?? false,
        channel: res.data.channel ?? 'email',
        due_threshold: res.data.due_threshold ?? 5,
      });
    } catch { /* endpoint not available yet */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put('/users/institution/me/notification-config/', config);
      toast.success('通知配置已保存');
    } catch { toast.error('保存失败'); }
    finally { setSaving(false); }
  };

  if (loading) return null;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">到期复习提醒</h3>
        </div>
      </div>

      <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] p-6 space-y-6">
        {/* Enable toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label className="text-sm font-semibold">启用到期提醒</Label>
            <p className="text-xs text-[#8E8E93]">
              学生有多道到期复习题时自动通知他们回来练习
            </p>
          </div>
          <Switch
            checked={config.enabled}
            onCheckedChange={(v) => setConfig({ ...config, enabled: v })}
          />
        </div>

        {config.enabled && (
          <>
            {/* Channel */}
            <div className="space-y-3">
              <Label className="text-sm font-semibold">通知渠道</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setConfig({ ...config, channel: 'email' })}
                  className={`flex items-center gap-3 p-4 rounded-xl border-2 text-left transition-all ${
                    config.channel === 'email'
                      ? 'border-[#0071E3] bg-[#0071E3]/[0.04]'
                      : 'border-black/[0.06] hover:border-black/[0.12]'
                  }`}
                >
                  <Envelope className={`h-5 w-5 ${config.channel === 'email' ? 'text-[#0071E3]' : 'text-[#AEAEB2]'}`} />
                  <div>
                    <p className="text-sm font-medium">邮件</p>
                    <p className="text-[11px] text-[#8E8E93]">发送到学生注册邮箱</p>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setConfig({ ...config, channel: 'feishu' })}
                  disabled
                  className="flex items-center gap-3 p-4 rounded-xl border-2 border-black/[0.06] text-left opacity-40 cursor-not-allowed"
                >
                  <span className="text-lg">🕊</span>
                  <div>
                    <p className="text-sm font-medium">飞书</p>
                    <p className="text-[11px] text-[#8E8E93]">即将支持</p>
                  </div>
                </button>
              </div>
            </div>

            {/* Threshold */}
            <div className="space-y-2">
              <Label className="text-sm font-semibold">触发阈值</Label>
              <p className="text-xs text-[#8E8E93]">
                学生到期题目数量超过此值时发送提醒
              </p>
              <Input
                type="number"
                min={1}
                max={100}
                value={config.due_threshold}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v)) setConfig({ ...config, due_threshold: Math.max(1, Math.min(100, v)) });
                }}
                className="w-24 h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 text-sm font-medium text-center"
              />
            </div>
          </>
        )}

        {/* Save */}
        <Button
          onClick={handleSave}
          disabled={saving}
          className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-6 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2"
        >
          {saving && <Spinner className="h-4 w-4 animate-spin" />}
          保存配置
        </Button>
      </Card>
    </div>
  );
};
