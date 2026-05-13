import React, { useState, useEffect } from 'react';
import { Download, File, CheckSquare, Square, Loader2, Info } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { PageWrapper } from '@/components/PageWrapper';
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent } from "@/components/ui/card";

const StartupMaterials: React.FC = () => {
  const [files, setFiles] = useState<any[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/courses/startup-materials/')
      .then(res => setFiles(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const toggleSelection = (id: number) => {
    const newSelection = new Set(selectedFiles);
    if (newSelection.has(id)) {
      newSelection.delete(id);
    } else {
      newSelection.add(id);
    }
    setSelectedFiles(newSelection);
  };

  const handleDownload = () => {
    selectedFiles.forEach(id => {
      const file = files.find(f => f.id === id);
      if (file) {
        window.open(file.file, '_blank');
      }
    });
  };

  if (loading) return <div className="h-[60vh] flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-black/10" /></div>;

  return (
    <PageWrapper 
      title="启动资料" 
      subtitle="精选的必备文档与工具，在这里开始起飞"
      action={
        <Button 
          onClick={handleDownload} 
          disabled={selectedFiles.size === 0}
          className="rounded-xl font-bold bg-primary text-primary-foreground h-9 text-xs"
        >
          <Download className="mr-2 h-3.5 w-3.5" />
          下载选中 ({selectedFiles.size})
        </Button>
      }
    >
      <div className="space-y-6 animate-in fade-in duration-500">
        {/* User Guide Card */}
        <Card className="border-none shadow-sm bg-gradient-to-br from-indigo-50 to-white border border-indigo-100/50 rounded-3xl overflow-hidden">
          <CardContent className="p-6 flex items-start gap-4">
            <div className="h-10 w-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <Info className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-indigo-950 uppercase tracking-widest">使用指南</h3>
              <p className="text-xs text-indigo-900/70 font-medium leading-relaxed max-w-3xl">
                欢迎下载启动资料，这是用于金融硕士入门必备的一些教材、课件、工具等，由我们精选并对外公开展示。请选中你想要下载的文件（支持多选），然后点击右上角的“下载选中”按钮进行批量获取。
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {files.map((file) => (
            <div 
              key={file.id}
              onClick={() => toggleSelection(file.id)}
              className={cn(
                "group relative flex items-start p-4 rounded-2xl border cursor-pointer transition-all duration-200 hover:shadow-md bg-card",
                selectedFiles.has(file.id) 
                  ? "border-primary bg-primary/5" 
                  : "border-border/50 hover:border-primary/30"
              )}
            >
              <div className="h-10 w-10 rounded-lg bg-background flex items-center justify-center border border-border mr-3 shadow-sm shrink-0">
                <File className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1 min-w-0 pr-6">
                <p className="font-bold text-sm truncate text-foreground">{file.name}</p>
                {file.description && (
                  <p className="text-[10px] text-muted-foreground mt-1 line-clamp-2 leading-tight">{file.description}</p>
                )}
                <p className="text-[9px] text-muted-foreground/50 mt-2 uppercase font-bold tracking-wider">
                  {new Date(file.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="absolute top-4 right-4">
                <Checkbox 
                  checked={selectedFiles.has(file.id)}
                  onCheckedChange={() => toggleSelection(file.id)}
                  className={cn("rounded-md data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground border-muted-foreground/30")}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
      
      {files.length === 0 && (
        <EmptyState icon={File} title="暂无资料" className="h-64 border-2 border-dashed border-border/50 rounded-3xl bg-muted/10 mt-6" />
      )}
    </PageWrapper>
  );
};

export default StartupMaterials;
