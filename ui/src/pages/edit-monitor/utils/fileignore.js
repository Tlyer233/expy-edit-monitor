/**
 * fileignore 纯函数工具集
 * @description 从原 FileTree.jsx 拆出的纯函数：glob 匹配 / 忽略建议 / 可见目录计算
 */
import picomatch from 'picomatch' // glob 模式匹配（纯浏览器兼容，零 Node 依赖）

/** 需要特殊处理的后缀/前缀字符（如 *~.md, ~* 等） */
const SPECIAL_CHARS = ['~', '$']

/**
 * 生成文件级 fileignore 建议：文件名 / 后缀 / 特殊字符组合
 * @param {string} filepath 文件完整路径
 * @returns {{label:string, pattern:string}[]} 建议列表
 */
export function getFileIgnoreSuggestions(filepath) {
  const name = filepath.split('/').pop() // 文件名
  const dot = name.lastIndexOf('.') // 最后一个 .
  const base = dot > 0 ? name.slice(0, dot) : name // 不含后缀的部分
  const ext = dot > 0 ? name.slice(dot) : '' // 后缀（含 .）
  const items = [{ label: name, pattern: name }] // ① 完整文件名
  if (ext) items.push({ label: `*${ext}`, pattern: `*${ext}` }) // ② 后缀通配
  for (const ch of SPECIAL_CHARS) { // ③ 遍历特殊字符
    if (base.startsWith(ch)) { items.push({ label: `${ch} 开头 ${ext}`, pattern: `${ch}*${ext}` }, { label: `${ch} 开头`, pattern: `${ch}*` }) } // 前缀
    if (base.endsWith(ch)) { items.push({ label: `${ch} 结尾 ${ext}`, pattern: `*${ch}${ext}` }, { label: `${ch} 结尾`, pattern: `*${ch}` }) } // 后缀
  }
  return items
}

/**
 * 生成文件夹忽略候选（/a/b/*）
 * @param {string} filepath 文件路径
 * @returns {string[]} 候选模式
 */
export function getFolderIgnoreOptions(filepath) {
  const parts = filepath.replace(/\/$/, '').split('/').filter(Boolean) // 路径段
  const options = [] // 结果
  let accum = '' // 累积前缀
  for (let i = 0; i < parts.length - 1; i++) { // 不含文件名
    accum += '/' + parts[i] // 累加
    if (accum) { // 非空
      options.push(accum + '/*') // 目录通配
    }
  }
  return options.reverse() // 从深到浅
}

/**
 * glob 匹配：利用 picomatch 检查 fileignore 规则是否命中文件路径
 * @param {string} filepath 文件完整路径
 * @param {string[]} fileignores 忽略规则列表（支持所有 POSIX glob 模式：*、**、?、[...] 等）
 * @returns {boolean} 是否命中忽略规则
 * @doc https://github.com/micromatch/picomatch
 */
export function matchFileignore(filepath, fileignores) {
  if (!fileignores || !fileignores.length) return false // 无规则直接返回
  const basename = filepath.split('/').pop() // 文件名（如 555~.md）
  const hit = fileignores.some(p => { // 三层匹配（dot: true 让 * 匹配 .开头的目录/文件）
    if (picomatch.isMatch(filepath, p, { dot: true })) return true // 全路径匹配
    if (picomatch.isMatch(basename, p, { dot: true })) return true // 文件名匹配
    if (p.endsWith('/*')) return picomatch.isMatch(filepath, p.replace(/\/\*$/, '/**'), { dot: true }) // /path/* → /path/** 递归匹配子目录
    return false
  })
  if (hit) console.log('[FileTree-ignore]', filepath, '←', fileignores) // 命中日志（调试用）
  return hit
}

/**
 * 底部向上计算可见目录：目录可见 = 至少有一个子孙未被 fileignore 命中
 * @param {object} node 树根节点
 * @param {string[]} fileignores 忽略规则
 * @returns {Set<string>} 可见目录路径集合
 */
export function computeVisibleDirs(node, fileignores) {
  const result = new Set() // 结果集
  function walk(n) { // 递归 walk，返回当前目录是否可见
    let hasVisibleFile = false // 是否有不被忽略的文件
    for (const f of n.files || []) { // 遍历本层文件
      if (!matchFileignore(f.filepath, fileignores)) hasVisibleFile = true // 有不被忽略的文件
    }
    let hasVisibleChild = false // 是否有可见子目录
    for (const child of n.children || []) { // 遍历子目录
      if (walk(child)) hasVisibleChild = true // 子目录可见
    }
    const visible = hasVisibleFile || hasVisibleChild // 有可见内容才显示
    if (visible) result.add(n.path) // 记入可见集
    return visible // 返回给上层
  }
  walk(node) // 启动递归
  result.add(node.path) // 根节点始终可见
  return result // 返回 Set
}
