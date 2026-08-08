/**
 * 平铺发现数据 → 嵌套文件树
 * @description 阶段 2 新增；接收后端 /discovered 平铺数据 [{file_path, hit_count}]，
 *              复刻原 api/router.py 的建树逻辑（公共根前缀 + 目录聚合 + count 汇总 + 按 count 降序）
 */

/**
 * 路径逐级前缀列表（不含空）
 * @param {string} p 文件路径
 * @returns {string[]} 前缀列表（如 /a /a/b ...）
 */
function pathPrefixes(p) {
  const parts = p.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean) // 分段（去首尾斜杠、去空段）
  const out = [] // 前缀集合
  for (let i = 0; i < parts.length; i++) { // 逐级拼接
    out.push('/' + parts.slice(0, i + 1).join('/')) // /a /a/b ...
  }
  return out // 返回
}

/**
 * 递归汇总节点 count = 文件 hit 之和 + 子目录 count
 * @param {object} node 节点（children 为 dict）
 * @returns {number} 总数
 */
function accumulate(node) {
  let total = (node.files || []).reduce((s, f) => s + (f.hit_count || 0), 0) // 本层文件
  for (const child of Object.values(node.children || {})) { // 子目录
    total += accumulate(child) // 递归
  }
  node.count = total // 写回
  return total // 返回总数
}

/**
 * children dict → 按 count 降序 list，递归
 * @param {object} node 节点（children 为 dict）
 * @returns {object} 列表节点
 */
function toList(node) {
  const children = Object.values(node.children || {}) // 子 map 取值
    .map(toList) // 递归转换
    .sort((a, b) => (b.count || 0) - (a.count || 0)) // 按 count 降序（V8 sort 稳定，与原 Python sorted 一致）
  return { // 列表节点
    name: node.name, // 目录名
    path: node.path, // 完整路径
    count: node.count, // 命中汇总
    children, // 子目录列表
    files: node.files || [], // 文件列表
  }
}

/**
 * 平铺记录 → 嵌套树（无数据返回空树，格式与后端原返回一致）
 * @param {Array<{file_path:string, hit_count:number}>} rows 平铺数据
 * @returns {{name:string, path:string, count:number, children:Array, files:Array}} 树结构
 */
export default function buildTree(rows) {
  if (!rows || !rows.length) { // 无数据
    return { name: '', path: '', count: 0, children: [], files: [] } // 空树
  }

  // ① 计算公共根前缀（按目录段，顺序敏感：一旦断开后面也断）
  const prefixSets = rows.map(r => pathPrefixes(r.file_path)) // 每条前缀链
  let common = prefixSets[0] ? [...prefixSets[0]] : [] // 以第一条为基准
  for (let i = 1; i < prefixSets.length; i++) { // 与其余求交
    const keep = [] // 仍公共的前缀
    for (const c of common) { // 逐个检查
      if (prefixSets[i].includes(c)) { // 仍在
        keep.push(c) // 保留
      } else {
        break // 一旦断开后面也断
      }
    }
    common = keep // 更新
    if (!common.length) break // 无公共
  }

  const rootPath = common.length ? common[common.length - 1] : '/' // 公共根路径
  const rootName = rootPath.replace(/\/+$/, '').split('/').filter(Boolean).pop() || '/' // 根显示名
  const rootDepth = rootPath === '/' ? 0 : rootPath.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean).length // 根深度
  const root = { // 根节点（children 暂用 dict）
    name: rootName, // 根名
    path: rootPath, // 根路径
    count: 0, // 汇总（后算）
    children: {}, // 子 map
    files: [], // 文件
  }

  // ② 逐条挂入树
  for (const r of rows) { // 遍历每条文件记录
    const filepath = r.file_path // 文件路径
    const hitCount = r.hit_count // 命中次数
    const parts = filepath.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean) // 路径段
    let node = root // 从根走
    for (let i = rootDepth; i < parts.length - 1; i++) { // 目录段（根之上跳过）
      const part = parts[i] // 段名
      const currentPath = '/' + parts.slice(0, i + 1).join('/') // 完整路径
      const children = node.children // 子 map
      if (!children[part]) { // 新建子目录
        children[part] = { // 节点
          name: part, // 目录名
          path: currentPath, // 完整路径
          count: 0, // 汇总（后算）
          children: {}, // 子 map
          files: [], // 文件
        }
      }
      node = children[part] // 下钻
    }
    node.files.push({ filepath, hit_count: hitCount }) // 挂文件
  }

  // ③ 汇总 count + children 转 list
  accumulate(root) // 汇总 count
  return toList(root) // children 转 list 返回
}
