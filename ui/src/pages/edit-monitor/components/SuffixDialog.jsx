/**
 * 后缀选择弹窗
 * @description 从原 FileTree.jsx 拆出；添加新应用时按分组多选监控后缀
 */
import { POSTFIX_GROUPS } from '../constants' // 常用后缀分组
import { Button } from '@/components/ui/button' // 按钮
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog' // 对话框
import Checkbox from './Checkbox' // 简易复选框
import useEditMonitorStore from '../store' // 共享状态

/**
 * 后缀选择弹窗（添加新应用流程第二步）
 * @returns {JSX.Element|null}
 */
export default function SuffixDialog() {
  const suffixDialog = useEditMonitorStore(s => s.suffixDialog) // 弹窗数据
  const suffixSelections = useEditMonitorStore(s => s.suffixSelections) // 后缀多选结果
  const setSuffixSelections = useEditMonitorStore(s => s.setSuffixSelections) // 更新多选
  const confirmAddApp = useEditMonitorStore(s => s.confirmAddApp) // 确认添加

  return (
    <Dialog open={!!suffixDialog} onOpenChange={v => { if (!v) setSuffixDialog(null) }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>选择文件后缀</DialogTitle>
          <DialogDescription>
            为「{suffixDialog?.app?.name}」选择需要监控的文件后缀（可多选）
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 max-h-[50vh] overflow-auto">
          {POSTFIX_GROUPS.map((group, gi) => (
            <div key={gi}>
              <div className="text-xs font-medium text-(--muted-foreground) mb-1">{group.label}</div>
              <div className="flex flex-wrap gap-2">
                {group.options.map(opt => (
                  <Checkbox
                    key={opt}
                    label={opt}
                    checked={suffixSelections.includes(opt)} // 是否已选
                    onChange={checked => setSuffixSelections(prev => ( // 多选更新
                      checked ? [...prev, opt] : prev.filter(p => p !== opt)
                    ))}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { confirmAddApp() }}>跳过</Button>
          <Button onClick={confirmAddApp}>确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
