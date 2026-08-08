/**
 * 递归文件树节点
 * @description 从原 FileTree.jsx FileTreeNode 拆出；默认展开前两层，单子目录自动折叠路径
 */
import { useState } from 'react' // hooks
import { FolderOpen, ChevronRight, ChevronDown, File } from 'lucide-react' // 图标
import { matchFileignore } from '../utils/fileignore' // 忽略规则匹配
import useEditMonitorStore from '../store' // 共享状态

/**
 * 递归文件树节点
 * @param {object} props 属性
 * @param {object} props.node 树节点
 * @param {number} props.depth 深度
 * @param {string[]} props.fileignores 忽略规则
 * @param {Set<string>} props.visibleDirs 可见目录路径集合
 * @returns {JSX.Element}
 */
export default function FileTreeNode({ node, depth, fileignores, visibleDirs }) {
  const [open, setOpen] = useState(depth < 2) // 默认展开前两层
  const setPopover = useEditMonitorStore(s => s.setPopover) // 打开忽略/显示弹层
  const childrenArr = (node.children || []).filter(c => visibleDirs.has(c.path)) // 只渲染可见子目录
  const filesArr = (node.files || []).filter(f => !matchFileignore(f.filepath, fileignores)) // 只渲染未被忽略的文件

  if (childrenArr.length === 1 && !filesArr.length) { // 单子目录折叠路径
    const child = childrenArr[0] // 唯一子节点
    return (
      <FileTreeNode
        node={{ ...child, name: node.name + '/' + child.name }} // 合并路径名
        depth={depth} // 深度不变
        fileignores={fileignores} // 透传忽略
        visibleDirs={visibleDirs} // 可见目录集
      />
    )
  }

  return (
    <div>
      {depth >= 0 && ( // 目录行
        <div className="flex items-center gap-1 py-0.5 text-xs hover:bg-(--muted) rounded px-1">
          <button type="button" onClick={() => setOpen(!open)} className="p-0.5 hover:bg-(--secondary) rounded">
            {childrenArr.length || filesArr.length ? ( // 可展开
              open ? <ChevronDown className="w-3 h-3 text-(--muted-foreground)" /> : <ChevronRight className="w-3 h-3 text-(--muted-foreground)" />
            ) : <span className="w-3 h-3" />}
          </button>
          <FolderOpen className="w-3.5 h-3.5 shrink-0 text-(--warning)" />
          <span className="truncate flex-1">{node.name}</span>
          <span className="text-[10px] text-(--muted-foreground) shrink-0">{node.count}</span>
        </div>
      )}
      {open && childrenArr.length > 0 && ( // 子目录（带边框树状线）
        <div className="ml-2.5 border-l border-(--border) pl-2">
          {childrenArr.map(child => (
            <FileTreeNode
              key={child.path} // 路径 key
              node={child} // 子节点
              depth={depth + 1} // 加深
              fileignores={fileignores} // 透传
              visibleDirs={visibleDirs} // 可见目录集
            />
          ))}
        </div>
      )}
      {open && filesArr.length > 0 && filesArr.map(f => ( // 文件行（简单左缩进，无边框线）
        <div
          key={f.filepath} // 路径 key
          className="flex items-center gap-1 py-0.5 text-xs group hover:bg-(--muted) rounded px-1 ml-8"
        >
          <File className="w-3 h-3 shrink-0 text-(--tag-patch-sfl-text)" />
          <span className="truncate flex-1">{f.filepath.split('/').pop()}</span>
          <span className="text-[10px] text-(--muted-foreground) shrink-0">{f.hit_count}</span>
          <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              onClick={() => setPopover({ type: 'folder', filepath: f.filepath })} // 忽略规则
              title="忽略规则"
              className="p-0.5 hover:bg-(--accent) rounded text-(--muted-foreground) hover:text-(--destructive)"
            >
              <FolderOpen className="w-2.5 h-2.5" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
