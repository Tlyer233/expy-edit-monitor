/**
 * 简易复选框
 * @description 从原 FileTree.jsx Checkbox 拆出；label + checkbox 原生样式
 */
/**
 * 简易复选框
 * @param {object} props 属性
 * @param {boolean} props.checked 是否勾选
 * @param {Function} props.onChange 变更回调
 * @param {string} [props.label] 文案
 * @returns {JSX.Element}
 */
export default function Checkbox({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-1.5 cursor-pointer text-xs">
      <input
        type="checkbox"
        checked={checked} // 勾选态
        onChange={e => onChange(e.target.checked)} // 回传 boolean
        className="w-3.5 h-3.5 rounded border-(--border) text-(--primary) focus:ring-(--primary)"
      />
      {label && <span>{label}</span>} {/* 可选标签 */}
    </label>
  )
}
