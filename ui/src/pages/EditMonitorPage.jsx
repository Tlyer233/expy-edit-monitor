/**
 * EditMonitor 配置页入口
 * @description 组装侧栏 + 主界面；状态在 Zustand store
 */
import { useEffect } from 'react' // 生命周期
import { Loader2 } from 'lucide-react' // 加载图标
import useEditMonitorStore from './edit-monitor/store' // 共享状态
import Sidebar from './edit-monitor/Sidebar' // 侧栏
import MainPanel from './edit-monitor/MainPanel' // 主界面

/**
 * 编辑监控配置页
 * @returns {JSX.Element}
 */
export default function EditMonitorPage() {
  const loading = useEditMonitorStore(s => s.loading) // 首屏加载
  const config = useEditMonitorStore(s => s.config) // 配置
  const selectedAppIndex = useEditMonitorStore(s => s.selectedAppIndex) // 选中下标
  const loadConfig = useEditMonitorStore(s => s.loadConfig) // 拉配置
  const loadDiscovered = useEditMonitorStore(s => s.loadDiscovered) // 拉文件树

  useEffect(() => { // 挂载拉配置
    loadConfig() // 首屏
  }, [loadConfig]) // 稳定引用

  useEffect(() => { // 切换应用时拉 discovered
    if (!config || selectedAppIndex === null) return // 未就绪
    loadDiscovered() // 拉树
  }, [config, selectedAppIndex, loadDiscovered]) // 依赖选中与配置

  if (loading) { // 加载中
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-(--muted-foreground)" />
      </div>
    )
  }

  if (!config) { // 加载失败
    return <div className="p-4 text-(--muted-foreground) text-sm">加载失败</div>
  }

  return (
    <div className="flex h-full min-h-0 relative bg-(--background) text-(--foreground)">
      <Sidebar /> {/* 左侧应用列表 */}
      <MainPanel /> {/* 右侧配置 + 文件树 + 保存 */}
    </div>
  )
}
