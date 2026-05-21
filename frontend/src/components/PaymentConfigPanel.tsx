import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Loader2, Save, ShieldCheck } from 'lucide-react';

export function PaymentConfigPanel() {
  const [cfg, setCfg] = useState({
    is_enabled: false,
    wechat_merchant_id: '',
    wechat_api_v3_key: '',
    wechat_cert_serial: '',
    alipay_app_id: '',
    alipay_private_key: '',
    wechat_has_key: false,
    alipay_has_key: false,
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchConfig(); }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/users/institution/me/payment-config/');
      setCfg(data);
    } catch {
      toast.error('加载收款配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: any = {
        is_enabled: cfg.is_enabled,
        wechat_merchant_id: cfg.wechat_merchant_id,
        wechat_cert_serial: cfg.wechat_cert_serial,
        alipay_app_id: cfg.alipay_app_id,
      };
      if (cfg.wechat_api_v3_key) payload.wechat_api_v3_key = cfg.wechat_api_v3_key;
      if (cfg.alipay_private_key) payload.alipay_private_key = cfg.alipay_private_key;

      await api.put('/users/institution/me/payment-config/', payload);
      toast.success('收款配置已保存');
      fetchConfig(); // refresh to get has_key status
    } catch (e: any) {
      toast.error(e?.response?.data?.error || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-amber-100 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-amber-600" />
          </div>
          <div>
            <h3 className="font-extrabold text-sm text-foreground">学生端收费</h3>
            <p className="text-[12px] text-muted-foreground font-medium">学生付款直进自有商户号，平台不参与分账</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Label className="text-[11px] font-bold text-muted-foreground">启用</Label>
          <Switch checked={cfg.is_enabled} onCheckedChange={(v) => setCfg({ ...cfg, is_enabled: v })} />
        </div>
      </div>

      <Separator />

      {/* WeChat Pay */}
      <div className="space-y-4">
        <h4 className="text-xs font-extrabold text-foreground/60 uppercase tracking-widest">微信支付</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-[11px] font-bold text-muted-foreground">微信商户号</Label>
            <Input
              value={cfg.wechat_merchant_id}
              onChange={(e) => setCfg({ ...cfg, wechat_merchant_id: e.target.value })}
              placeholder="1xxxxxxxxx"
              className="h-10 rounded-xl text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px] font-bold text-muted-foreground">证书序列号</Label>
            <Input
              value={cfg.wechat_cert_serial}
              onChange={(e) => setCfg({ ...cfg, wechat_cert_serial: e.target.value })}
              placeholder="证书序列号"
              className="h-10 rounded-xl text-sm"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-[11px] font-bold text-muted-foreground">
            APIv3 Key {cfg.wechat_has_key && <span className="text-unimind-green ml-1">(已设置)</span>}
          </Label>
          <Input
            type="password"
            value={cfg.wechat_api_v3_key}
            onChange={(e) => setCfg({ ...cfg, wechat_api_v3_key: e.target.value })}
            placeholder={cfg.wechat_has_key ? '留空则不修改' : '微信 APIv3 密钥'}
            className="h-10 rounded-xl text-sm font-mono"
          />
        </div>
      </div>

      <Separator />

      {/* Alipay */}
      <div className="space-y-4">
        <h4 className="text-xs font-extrabold text-foreground/60 uppercase tracking-widest">支付宝</h4>
        <div className="space-y-1.5">
          <Label className="text-[11px] font-bold text-muted-foreground">支付宝 App ID</Label>
          <Input
            value={cfg.alipay_app_id}
            onChange={(e) => setCfg({ ...cfg, alipay_app_id: e.target.value })}
            placeholder="2xxxxxxxxx"
            className="h-10 rounded-xl text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-[11px] font-bold text-muted-foreground">
            应用私钥 {cfg.alipay_has_key && <span className="text-unimind-green ml-1">(已设置)</span>}
          </Label>
          <Input
            type="password"
            value={cfg.alipay_private_key}
            onChange={(e) => setCfg({ ...cfg, alipay_private_key: e.target.value })}
            placeholder={cfg.alipay_has_key ? '留空则不修改' : '支付宝应用私钥 (RSA2)'}
            className="h-10 rounded-xl text-sm font-mono"
          />
        </div>
      </div>

      <Button onClick={handleSave} disabled={saving} className="w-full h-11 rounded-xl font-extrabold gap-2">
        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
        保存收款配置
      </Button>
    </div>
  );
}
