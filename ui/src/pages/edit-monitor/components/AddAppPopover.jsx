/**
 * 添加应用列表弹层
 * @description 从原 FileTree.jsx 拆出；列出本机可添加 App，点选进入后缀选择或恢复
 */
import { Search } from 'lucide-react' // 图标
import SimplePopover from './SimplePopover' // 简易居中弹层
import useEditMonitorStore from '../store' // 共享状态

/**
 * 添加应用 Popover（由侧栏底部 + 按钮触发）
 * @returns {JSX.Element|null}
 */
export default function AddAppPopover() {
  const addAppPopover = useEditMonitorStore(s => s.addAppPopover) // 是否打开
  const macApps = useEditMonitorStore(s => s.macApps) // 本机可添加 App 列表
  const setAddAppPopover = useEditMonitorStore(s => s.setAddAppPopover) // 关闭弹层
  const selectAppForAdd = useEditMonitorStore(s => s.selectAppForAdd) // 选中待添加应用

  return (
    <SimplePopover open={addAppPopover} onClose={() => setAddAppPopover(false)}>
      <div className="text-xs font-medium mb-2 text-(--foreground) flex items-center gap-2">
        <Search className="w-3 h-3" />选择要添加的应用
      </div>
      <div className="space-y-0.5 overflow-auto max-h-[400px]">
        {macApps.length === 0 && (
          <div className="text-xs text-(--muted-foreground) py-4 text-center">没有更多可添加的应用</div>
        )}
        {macApps.map(app => (
          <button
            key={app.exec_path}
            type="button"
            onClick={() => selectAppForAdd(app)} // 选中
            className="w-full flex items-center gap-2 text-left text-xs px-2 py-1.5 hover:bg-(--secondary) rounded"
          >
            <span className="flex-1">{app.name}</span>
          </button>
        ))}
      </div>
    </SimplePopover>
  )
}
