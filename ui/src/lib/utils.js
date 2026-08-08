import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Tailwind class 合并工具（shadcn 依赖） */
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
