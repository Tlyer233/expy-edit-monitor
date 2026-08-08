/**
 * 标签编辑器
 * @description 从原 FileTree.jsx TagEditor 拆出；本地编辑完成后才 onChange 回传
 */
import { useState } from 'react' // hooks
import { X } from 'lucide-react' // 图标
import { Input } from '@/components/ui/input' // 输入框

/**
 * 标签列表本地编辑器（完成后才 onChange）
 * @param {object} props 属性
 * @param {string[]} props.items 当前项
 * @param {Function} props.onChange 完成回调
 * @param {string} props.placeholder 输入占位
 * @returns {JSX.Element}
 */
export default function TagEditor({ items, onChange, placeholder }) {
  const [editing, setEditing] = useState(false) // 是否编辑中
  const [text, setText] = useState('') // 输入文本
  const [localItems, setLocalItems] = useState([...items]) // 本地副本

  /**
   * 进入编辑
   * @returns {void}
   */
  function startEdit() {
    setLocalItems([...items]) // 同步外部
    setEditing(true) // 开编辑
  }

  /**
   * 添加一项
   * @returns {void}
   */
  function addItem() {
    const trimmed = text.trim() // 去空白
    if (trimmed && !localItems.includes(trimmed)) { // 非空且不重复
      setLocalItems([...localItems, trimmed]) // 追加
      setText('') // 清空输入
    }
  }

  /**
   * 删除一项
   * @param {number} idx 下标
   * @returns {void}
   */
  function removeItem(idx) {
    setLocalItems(localItems.filter((_, i) => i !== idx)) // 过滤
  }

  /**
   * 完成编辑并回传
   * @returns {void}
   */
  function handleDone() {
    onChange(localItems) // 回传
    setEditing(false) // 关编辑
  }

  if (!editing) { // 只读展示
    return (
      <div className="flex items-center gap-1 flex-wrap min-h-[24px]">
        {items.map((item, i) => (
          <span key={i} className="text-xs px-1.5 py-0.5 bg-(--muted) rounded">{item}</span>
        ))}
        <button
          type="button"
          onClick={startEdit} // 进入编辑
          className="text-xs px-1.5 py-0.5 border border-dashed border-(--border) rounded hover:border-(--primary) text-(--muted-foreground) hover:text-(--foreground)"
        >
          + 编辑
        </button>
      </div>
    )
  }

  return ( // 编辑态
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1 flex-wrap">
        {localItems.map((item, i) => (
          <span key={i} className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 bg-(--muted) rounded group">
            {item}
            <button type="button" onClick={() => removeItem(i)} className="opacity-0 group-hover:opacity-100 hover:text-(--destructive)">
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex items-center gap-1">
        <Input
          value={text} // 输入
          onChange={e => setText(e.target.value)} // 同步
          onKeyDown={e => e.key === 'Enter' && addItem()} // 回车添加
          placeholder={placeholder} // 占位
          className="h-6 text-xs flex-1"
        />
        <button type="button" onClick={addItem} className="text-xs px-1.5 py-0.5 bg-(--secondary) rounded hover:bg-(--muted)">添加</button>
        <button type="button" onClick={handleDone} className="text-xs px-1.5 py-0.5 bg-(--primary) text-(--primary-foreground) rounded hover:brightness-90">完成</button>
        <button type="button" onClick={() => setEditing(false)} className="text-xs px-1.5 py-0.5 bg-(--secondary) rounded hover:bg-(--muted)">取消</button>
      </div>
    </div>
  )
}
