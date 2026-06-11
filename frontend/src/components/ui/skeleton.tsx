import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

function SkeletonLine({ width = "w-full", className }: { width?: string; className?: string }) {
  return <Skeleton className={cn("h-4", width, className)} />
}

function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-3 rounded-xl border border-border/50 p-5", className)}>
      <Skeleton className="h-40 w-full rounded-lg" />
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  )
}

export { Skeleton, SkeletonLine, SkeletonCard }
