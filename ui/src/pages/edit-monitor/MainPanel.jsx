/**
 * 主界面：应用信息 + 后缀/忽略编辑 + 文件树 + 保存/取消
 * @description 状态全部走 Zustand
 */
import { Loader2, Check } from 'lucide-react' // 图标
import { Switch } from '@/components/ui/switch' // 开关
import { Button } from '@/components/ui/button' // 按钮
import useEditMonitorStore from './store' // 共享状态
import FileTree, { TagEditor } from './FileTree' // 文件树 + 标签编辑器
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs' // Tab 切换

/**
 * 右侧主配置区
 * @returns {JSX.Element}
 */
export default function MainPanel() {
  const dirty = useEditMonitorStore(s => s.dirty) // 未保存
  const saving = useEditMonitorStore(s => s.saving) // 保存中
  const selectedAppIndex = useEditMonitorStore(s => s.selectedAppIndex) // 选中下标（触发重渲染）
  const config = useEditMonitorStore(s => s.config) // 配置（保存用 + 触发重渲染）
  const loadConfig = useEditMonitorStore(s => s.loadConfig) // 取消=重载
  const saveConfigNow = useEditMonitorStore(s => s.saveConfigNow) // 保存
  const toggleApp = useEditMonitorStore(s => s.toggleApp) // 顶栏开关
  const updatePostfixLocal = useEditMonitorStore(s => s.updatePostfixLocal) // 改后缀
  const updateFileignoreLocal = useEditMonitorStore(s => s.updateFileignoreLocal) // 改忽略
  const getCurrentApp = useEditMonitorStore(s => s.getCurrentApp) // 当前应用

  const currentApp = getCurrentApp() // 依赖 config/selectedAppIndex 订阅后重算

  if (!currentApp) { // 未选中
    return (
      <div className="flex-1 flex items-center justify-center h-full text-(--muted-foreground) text-sm">
        请从左侧选择一个应用
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
      <div className="flex flex-col flex-1 min-h-0">
        {/* 应用头 */}
        <div className="flex items-center gap-3 p-3 border-b border-(--border) shrink-0">
          <span className="font-semibold text-sm">{currentApp.displayName}</span>
          <span
            className="text-xs px-1.5 py-0.5 bg-(--muted) rounded text-(--muted-foreground) font-mono truncate"
            title={currentApp.app_path}
          >
            {currentApp.app_path}
          </span>
          <div className="ml-auto flex items-center gap-2">
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin text-(--muted-foreground)" />}
            <Switch
              checked={currentApp.enabled} // 是否启用
              onCheckedChange={() => toggleApp(selectedAppIndex)} // 切换 enabled
            />
          </div>
        </div>

        {/* 配置表单 + 文件树 */}
        <div className="flex-1 overflow-auto p-3 space-y-4">
          {/* 配置 Tabs：固定高度 + 滚动 */}
          <Tabs defaultValue="postfix" className="flex-1 flex flex-col min-h-0">
            <TabsList className="shrink-0">
              <TabsTrigger value="postfix" className="text-xs">文件后缀</TabsTrigger>
              <TabsTrigger value="ignore" className="text-xs">忽略规则</TabsTrigger>
            </TabsList>

            {/* 文件后缀 Tab */}
            <TabsContent value="postfix" className="flex-1 min-h-0 overflow-auto mt-0 data-[state=inactive]:hidden">
              <div className="pt-3">
                <TagEditor
                  items={currentApp.allow_postfix || []} // 当前后缀
                  onChange={updatePostfixLocal} // 本地改 + dirty
                  placeholder=".py"
                />
              </div>
            </TabsContent>

            {/* 忽略规则 Tab */}
            <TabsContent value="ignore" className="flex-1 min-h-0 overflow-auto mt-0 data-[state=inactive]:hidden">
              <div className="pt-3">
                <TagEditor
                  items={currentApp.fileignore || []} // 当前忽略
                  onChange={updateFileignoreLocal} // 本地改 + dirty
                  placeholder="*.log"
                />
              </div>
            </TabsContent>
          </Tabs>
          {/* 文件树区块（含弹窗） */}
          <FileTree />
        </div>
      </div>

      {/* 底部操作栏：布局内底栏（替代 fixed 悬浮，避免遮挡滚动内容） */}
      <div className="flex justify-end items-center gap-2 p-3 border-t border-(--border) shrink-0">
        <Button
          variant="outline"
          size="sm"
          disabled={!dirty} // 无改动禁用
          onClick={() => loadConfig()} // 取消=重拉配置
        >
          取消
        </Button>
        <Button
          size="sm"
          disabled={!dirty || saving} // 无改动或保存中禁用
          onClick={() => saveConfigNow(config)} // 保存当前 config
        >
          {saving
            ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
            : <Check className="w-3.5 h-3.5 mr-1" />}
          保存
        </Button>
      </div>
    </div>
  )
}
