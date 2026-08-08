/**
 * 侧栏：应用列表 + 折叠 + 添加/移除
 * @description 状态全部走 Zustand，不接收业务 props
 */
import { useMemo } from 'react' // 派生可见列表
import { ChevronRight, Plus, Minus } from 'lucide-react' // 图标
import { Switch } from '@/components/ui/switch' // 开关
import { cn } from '@/lib/utils' // className 合并
import useEditMonitorStore from './store' // 共享状态

/**
 * 应用列表侧栏
 * @returns {JSX.Element} 侧栏节点
 */
export default function Sidebar() {
  const config = useEditMonitorStore(s => s.config) // 完整配置
  const selectedAppIndex = useEditMonitorStore(s => s.selectedAppIndex) // 选中下标
  const sidebarCollapsed = useEditMonitorStore(s => s.sidebarCollapsed) // 是否折叠
  const toggleSidebarCollapsed = useEditMonitorStore(s => s.toggleSidebarCollapsed) // 折叠切换
  const switchApp = useEditMonitorStore(s => s.switchApp) // 切换应用
  const toggleApp = useEditMonitorStore(s => s.toggleApp) // 开关 enabled
  const openAddApp = useEditMonitorStore(s => s.openAddApp) // 打开添加
  const setAppDeleteDialog = useEditMonitorStore(s => s.setAppDeleteDialog) // 打开移除确认

  const getVisibleApps = useEditMonitorStore(s => s.getVisibleApps) // store 提供（与 store 同实现）
  const visibleApps = useMemo(() => getVisibleApps(), [getVisibleApps, config]) // 依赖 config 重算

  const currentApp = visibleApps[selectedAppIndex] || null // 当前选中应用

  return (
    <div className={cn( // 侧栏容器
      'flex flex-col border-r border-(--border) bg-(--muted) shrink-0 transition-all', // 布局样式
      sidebarCollapsed ? 'w-12' : 'w-52' // 折叠宽度
    )}>
      {/* 标题栏 */}
      <div className="flex items-center justify-between p-2 border-b border-(--border)">
        {!sidebarCollapsed && ( // 展开时显示标题
          <span className="text-xs font-medium text-(--muted-foreground)">应用列表</span>
        )}
        <button
          type="button"
          onClick={toggleSidebarCollapsed} // 折叠/展开
          className="p-1 hover:bg-(--secondary) rounded text-(--muted-foreground)"
        >
          <ChevronRight className={cn('w-4 h-4 transition-transform', !sidebarCollapsed && 'rotate-180')} />
        </button>
      </div>

      {/* 应用列表 */}
      <div className="flex-1 overflow-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        {visibleApps.map((app, i) => { // 遍历可见应用
          const isSelected = i === selectedAppIndex // 是否选中
          return (
            <button
              key={`${app.app_path || app.displayName}-${i}`} // 稳定 key
              type="button"
              onClick={() => switchApp(i)} // 切换选中
              className={cn(
                'w-full flex items-center gap-2 px-2 py-2 text-left transition-colors', // 行样式
                isSelected ? 'bg-[color-mix(in_oklch,var(--primary)_10%,transparent)] border-r-2 border-(--primary)' : 'hover:bg-(--secondary)', // 选中态（Tailwind v4 不支持 CSS 变量 + /10，用 color-mix 替代）
                !app.enabled && 'opacity-50' // 关闭半透明
              )}
            >
              {!sidebarCollapsed && ( // 展开：名称 + 开关
                <>
                  <span className="text-xs truncate flex-1">{app.displayName}</span>
                  <div
                    onClick={e => { // 阻止冒泡到选中
                      e.stopPropagation() // 不触发 switchApp
                      toggleApp(i) // 切换 enabled
                    }}
                    className="shrink-0"
                  >
                    <Switch checked={app.enabled} />
                  </div>
                </>
              )}
              {sidebarCollapsed && ( // 折叠：两字缩写
                <span className="text-[10px] text-(--muted-foreground) truncate w-full text-center">
                  {(app.displayName || '?').slice(0, 2)}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* 底部 +/- */}
      <div className="flex border-t border-(--border) p-1 gap-1">
        <button
          type="button"
          onClick={openAddApp} // 添加应用
          className="flex-1 flex items-center justify-center py-1 hover:bg-(--secondary) rounded text-(--muted-foreground) hover:text-(--foreground)"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => currentApp && setAppDeleteDialog(true)} // 打开移除确认
          disabled={!currentApp} // 无选中禁用
          className="flex-1 flex items-center justify-center py-1 hover:bg-(--secondary) rounded text-(--muted-foreground) hover:text-(--destructive) disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Minus className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
