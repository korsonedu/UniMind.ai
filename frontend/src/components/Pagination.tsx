import React from 'react';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({ page, totalPages, onPageChange }) => {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-3 py-3">
      <Button
        variant="outline"
        size="sm"
        className="h-8 rounded-lg text-xs"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft className="h-3.5 w-3.5 mr-1" />
        上一页
      </Button>
      <span className="text-xs text-muted-foreground font-medium">
        {page} / {totalPages}
      </span>
      <Button
        variant="outline"
        size="sm"
        className="h-8 rounded-lg text-xs"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        下一页
        <ChevronRight className="h-3.5 w-3.5 ml-1" />
      </Button>
    </div>
  );
};
