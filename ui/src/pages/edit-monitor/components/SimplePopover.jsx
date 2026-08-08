/**
 * 简易居中弹层
 * @description 从原 FileTree.jsx SimplePopover 拆出；遮罩 + 居中内容区
 */
/**
 * 简易居中弹层
 * @param {object} props 属性
 * @param {boolean} props.open 是否显示
 * @param {Function} props.onClose 关闭回调
 * @param {import('react').ReactNode} props.children 内容
 * @returns {JSX.Element|null}
 */
export default function SimplePopover({ open, onClose, children }) {
  if (!open) return null // 关闭不渲染
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} /> {/* 遮罩 */}
      <div
        onClick={e => e.stopPropagation()} // 内容区不关闭
        className="fixed z-50 left-1/2 top-1/3 -translate-x-1/2 bg-(--popover) rounded-lg shadow-lg border border-(--border) p-3 min-w-[280px] max-h-[60vh] flex flex-col"
      >
        {children}
      </div>
    </>
  )
}
