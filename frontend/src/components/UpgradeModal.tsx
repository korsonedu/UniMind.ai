import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface UpgradeModalProps { open: boolean; onOpenChange: (open: boolean) => void; feature?: string; currentPlan?: string; }

export function UpgradeModal({ open, onOpenChange }: UpgradeModalProps) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="sm:max-w-md rounded-lg">
    <DialogHeader><DialogTitle>我的服务</DialogTitle><DialogDescription>课程服务由科晟线下开通。你可以查看学员状态、每周问答额度和 AI 加量。</DialogDescription></DialogHeader>
    <Button asChild><a href="/billing">查看我的服务</a></Button>
  </DialogContent></Dialog>;
}
