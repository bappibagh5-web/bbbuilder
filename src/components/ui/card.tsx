import type{HTMLAttributes}from"react";import{cn}from"@/lib/utils";
export function Card({className,...props}:HTMLAttributes<HTMLDivElement>){return <div className={cn("rounded-xl border bg-card shadow-[0_1px_2px_rgba(16,24,40,.04)]",className)} {...props}/>}
