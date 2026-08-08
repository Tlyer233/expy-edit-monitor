/**
 * 忽略规则弹层
 * @description 从原 FileTree.jsx 拆出；文件夹候选 + 文件建议，点选后写入 fileignore
 */
import { getFolderIgnoreOptions, getFileIgnoreSuggestions } from '../utils/fileignore' // 忽略建议候选
import SimplePopover from './SimplePopover' // 简易居中弹层
import useEditMonitorStore from '../store' // 共享状态

/**
 * 忽略规则弹层（由文件树行内按钮触发）
 * @returns {JSX.Element|null}
 */
export default function IgnorePopover() {
  const config = useEditMonitorStore(s => s.config) // 订阅 config 以便改规则/切应用时重渲染
  const selectedAppIndex = useEditMonitorStore(s => s.selectedAppIndex) // 订阅选中下标
  const popover = useEditMonitorStore(s => s.popover) // 忽略弹层
  const setPopover = useEditMonitorStore(s => s.setPopover) // 关闭弹层
  const confirmIgnore = useEditMonitorStore(s => s.confirmIgnore) // 确认忽略
  const confirmShow = useEditMonitorStore(s => s.confirmShow) // 确认显示
  const getCurrentApp = useEditMonitorStore(s => s.getCurrentApp) // 便捷 getter

  void config // 参与订阅，触发重渲染
  void selectedAppIndex // 参与订阅，触发重渲染
  const currentApp = getCurrentApp() // 当前应用对象

  if (!currentApp || !popover) return null // 无目标不渲染

  const options = getFolderIgnoreOptions(popover.filepath) // 文件夹候选

  return (
    <SimplePopover open={true} onClose={() => setPopover(null)}>
      <div className="text-xs font-medium mb-2 text-(--foreground)">选择忽略规则</div>
      <div className="space-y-1 overflow-auto max-h-[300px]">
        {/* 文件夹候选 */}
        {options.map((opt, i) => (
          <button key={i} type="button"
            onClick={() => popover.type === 'folder' ? confirmIgnore(opt) : confirmShow(opt, 'folder')}
            className="w-full text-left text-xs px-2 py-1.5 hover:bg-(--secondary) rounded border border-(--border)">
            {opt}
          </button>
        ))}
        {/* 分隔线 + 文件建议 */}
        {popover.filepath && (
          <>
            <div className="border-t border-(--border) my-1" />
            {getFileIgnoreSuggestions(popover.filepath).map((s, i) => (
              <button key={`f-${i}`} type="button"
                onClick={() => confirmIgnore(s.pattern)}
                className="w-full text-left text-xs px-2 py-1.5 hover:bg-(--secondary) rounded border border-(--border)">
                {s.pattern}
              </button>
            ))}
          </>
        )}
      </div>
    </SimplePopover>
  )
}
