import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface UpgradeModalProps { open: boolean; onOpenChange: (open: boolean) => void; feature?: string; currentPlan?: string; }

export function UpgradeModal({ open, onOpenChange }: UpgradeModalProps) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="sm:max-w-md rounded-lg">
    <DialogHeader><DialogTitle>个人学习服务</DialogTitle><DialogDescription>基础学习免费开放。你可以查看个人课程权益和额外的 AI 对话额度。</DialogDescription></DialogHeader>
    <Button asChild><a href="/pricing">查看学习服务</a></Button>
  </DialogContent></Dialog>;
}
