/**
 * 文件树主组件（组装者）
 * @description 从原 FileTree.jsx 拆分后精简：发现文件区块 + 应用删除弹窗；其余弹窗/递归树/标签编辑均移到 components/
 */
import { useMemo } from 'react' // 派生计算
import { Loader2, RefreshCw } from 'lucide-react' // 图标
import { Button } from '@/components/ui/button' // 按钮
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog' // 对话框
import useEditMonitorStore from './store' // 共享状态
import FileTreeNode from './components/FileTreeNode' // 递归树节点
import TagEditor from './components/TagEditor' // 标签编辑器（re-export 供 MainPanel 沿用旧导入路径）
import IgnorePopover from './components/IgnorePopover' // 忽略规则弹层
import AddAppPopover from './components/AddAppPopover' // 添加应用弹层
import SuffixDialog from './components/SuffixDialog' // 后缀选择弹窗
import { computeVisibleDirs } from './utils/fileignore' // 可见目录计算

export { TagEditor } // 保持 MainPanel 的 `import { TagEditor } from './FileTree'` 兼容

/**
 * 发现文件树 + 相关弹窗（组装者）
 * @returns {JSX.Element}
 */
export default function FileTree() {
  const config = useEditMonitorStore(s => s.config) // 订阅 config 以便切换应用/改规则时重渲染
  const selectedAppIndex = useEditMonitorStore(s => s.selectedAppIndex) // 订阅选中下标
  const discovered = useEditMonitorStore(s => s.discovered) // 文件树数据
  const appDeleteDialog = useEditMonitorStore(s => s.appDeleteDialog) // 应用删除

  const setAppDeleteDialog = useEditMonitorStore(s => s.setAppDeleteDialog) // 应用删弹窗
  const confirmAppDelete = useEditMonitorStore(s => s.confirmAppDelete) // 确认移除应用
  const loadDiscovered = useEditMonitorStore(s => s.loadDiscovered) // 刷新树
  const getCurrentApp = useEditMonitorStore(s => s.getCurrentApp) // 当前应用

  void config // 参与订阅，触发重渲染
  void selectedAppIndex // 参与订阅，触发重渲染
  const currentApp = getCurrentApp() // 当前应用对象
  const fileignores = currentApp?.fileignore || [] // 忽略规则
  const visibleDirs = useMemo(() => { // 预计算可见目录（fileignores 或树变化时重算）
    if (!discovered) return new Set() // 无树数据返回空
    if (!fileignores.length) { // 无忽略规则 → 所有目录都可见
      const all = new Set() // 全集
      function collect(n) { all.add(n.path); (n.children || []).forEach(collect) } // 递归收集所有目录路径
      collect(discovered) // 从根开始
      return all // 返回全集
    }
    return computeVisibleDirs(discovered, fileignores) // 有规则时按规则过滤
  }, [discovered, fileignores]) // 依赖：发现树 / 忽略规则

  return (
    <>
      {/* 发现文件标题 + 刷新 */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-medium text-(--muted-foreground)">发现文件</span>
          <button
            type="button"
            onClick={() => loadDiscovered()} // 刷新 discovered
            className="p-0.5 hover:bg-(--secondary) rounded text-(--muted-foreground)"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
        <div className="border border-(--border) rounded-lg bg-(--background) p-2 max-h-[calc(100vh-400px)] overflow-auto">
          {discovered && discovered.count > 0 ? ( // 有数据
            visibleDirs.size <= 1 && fileignores.length > 0 ? ( // 全部被忽略规则过滤，只剩余根节点
              <div className="text-xs text-(--muted-foreground) py-4 text-center">所有文件已被忽略规则过滤</div>
            ) : ( // 有可见子节点，正常渲染树
              <FileTreeNode
                node={discovered} // 根节点
                depth={0} // 根深度
                fileignores={fileignores} // 忽略规则
                visibleDirs={visibleDirs} // 可见目录集
              />
            )
          ) : (
            <div className="text-xs text-(--muted-foreground) py-8 text-center">
              {discovered ? '暂无发现文件' : <Loader2 className="w-4 h-4 animate-spin mx-auto" />}
            </div>
          )}
        </div>
      </div>

      {/* 忽略 Popover（文件夹候选 + 文件建议） */}
      <IgnorePopover />

      {/* 应用删除弹窗 */}
      <Dialog open={!!appDeleteDialog} onOpenChange={v => { if (!v) setAppDeleteDialog(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认移除应用</DialogTitle>
            <DialogDescription>移除「{currentApp?.displayName}」后可通过底部 + 按钮恢复。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAppDeleteDialog(false)}>取消</Button>
            <Button variant="destructive" onClick={confirmAppDelete}>确认移除</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 添加应用 Popover（本机 App 列表） */}
      <AddAppPopover />

      {/* 后缀选择弹窗（添加新应用第二步） */}
      <SuffixDialog />
    </>
  )
}
