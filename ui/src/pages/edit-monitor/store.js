/**
 * EditMonitor Zustand 共享状态池
 * @description 侧栏 / 文件树 / 主界面 共用 config、选中应用、dirty 等状态
 */
import { create } from 'zustand' // Zustand 工厂
import buildTree from './utils/buildTree' // 平铺数据 → 嵌套树（后端去树化后前端自建）

const API = '/api/edit_monitor' // 业务 API 前缀

/**
 * 从 config 过滤可见应用并按 enabled 排序
 * @param {object|null} config 完整配置
 * @returns {Array} 可见应用列表
 */
function buildVisibleApps(config) {
  if (!config) return [] // 无配置返回空
  const apps = config.apps.filter(a => !a.is_delete) // 排除假删
  apps.sort((a, b) => { // enabled 优先
    if (a.enabled !== b.enabled) return a.enabled ? -1 : 1 // 开的在前
    return 0 // 同状态保持原序
  })
  return apps // 返回排序结果
}

/**
 * 根据可见列表下标取当前应用
 * @param {object|null} config 完整配置
 * @param {number|null} selectedAppIndex 可见列表下标
 * @returns {object|null} 当前应用
 */
function buildCurrentApp(config, selectedAppIndex) {
  if (!config || selectedAppIndex === null) return null // 未选中
  const visible = buildVisibleApps(config) // 重算可见列表
  return visible[selectedAppIndex] || null // 按下标取
}

/**
 * EditMonitor 全局 store
 */
const useEditMonitorStore = create((set, get) => ({
  // ── 数据 ──
  config: null, // 完整 config.json
  discovered: null, // 当前应用发现的文件树

  // ── 选中 / UI 状态 ──
  selectedAppIndex: null, // 可见应用列表下标
  sidebarCollapsed: false, // 侧栏是否折叠
  loading: true, // 首屏加载
  saving: false, // 保存中
  dirty: false, // 有未保存修改

  // ── 弹窗状态 ──
  popover: null, // { type, filepath } 忽略/显示弹层
  appDeleteDialog: false, // 应用移除确认
  addAppPopover: false, // 添加应用列表弹层
  macApps: [], // 本机可添加 App 列表
  suffixDialog: null, // { app, isRestore } 新应用后缀选择
  suffixSelections: [], // 后缀多选结果

  // ── 派生读取（组件内也可再算，这里提供便捷 getter）──
  /**
   * 获取可见应用列表
   * @returns {Array}
   */
  getVisibleApps: () => buildVisibleApps(get().config), // 从当前 config 过滤

  /**
   * 获取当前选中应用
   * @returns {object|null}
   */
  getCurrentApp: () => buildCurrentApp(get().config, get().selectedAppIndex), // 按下标取

  /**
   * 标记有未保存修改
   * @returns {void}
   */
  markDirty: () => set({ dirty: true }), // dirty=true

  /**
   * 切换侧栏折叠
   * @returns {void}
   */
  toggleSidebarCollapsed: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })), // 翻转

  /**
   * 设置弹层状态
   * @param {object|null} popover 弹层数据
   * @returns {void}
   */
  setPopover: (popover) => set({ popover }), // 直接覆盖

  /**
   * 设置应用删除弹窗
   * @param {boolean} open 是否打开
   * @returns {void}
   */
  setAppDeleteDialog: (open) => set({ appDeleteDialog: open }), // 布尔

  /**
   * 设置添加应用弹层
   * @param {boolean} open 是否打开
   * @returns {void}
   */
  setAddAppPopover: (open) => set({ addAppPopover: open }), // 布尔

  /**
   * 设置后缀选择弹窗
   * @param {object|null} suffixDialog 弹窗数据
   * @returns {void}
   */
  setSuffixDialog: (suffixDialog) => set({ suffixDialog }), // 直接覆盖

  /**
   * 设置后缀多选
   * @param {string[]|Function} next 新列表或 updater
   * @returns {void}
   */
  setSuffixSelections: (next) => set(s => ({ // 支持函数式更新
    suffixSelections: typeof next === 'function' ? next(s.suffixSelections) : next, // 兼容 prev =>
  })),

  /**
   * 加载 config.json
   * @returns {Promise<void>}
   * @api GET /api/edit_monitor/config
   */
  loadConfig: async () => {
    try {
      const r = await fetch(`${API}/config`).then(res => res.json()) // 拉配置
      const prevIndex = get().selectedAppIndex // 保留原选中
      const visible = buildVisibleApps(r) // 可见列表
      let nextIndex = prevIndex // 默认保留
      if (nextIndex === null && visible.length > 0) nextIndex = 0 // 首次默认第一项
      if (nextIndex !== null && nextIndex >= visible.length) nextIndex = visible.length ? 0 : null // 越界纠正
      set({ config: r, selectedAppIndex: nextIndex, dirty: false }) // 写回 store
    } catch (e) {
      console.error('config load fail', e) // 加载失败打日志
    } finally {
      set({ loading: false }) // 结束 loading
    }
  },

  /**
   * 切换选中应用；有脏数据时先重新拉配置丢弃本地改动
   * @param {number} index 可见列表下标
   * @returns {Promise<void>}
   */
  switchApp: async (index) => {
    if (get().dirty) { // 有未保存
      await get().loadConfig() // 先丢弃本地改动
      set({ selectedAppIndex: index }) // 再切应用
    } else {
      set({ selectedAppIndex: index }) // 直接切换
    }
  },

  /**
   * 按当前选中应用加载 discovered 文件树
   * @returns {Promise<void>}
   * @api GET /api/edit_monitor/discovered
   */
  loadDiscovered: async () => {
    const currentApp = get().getCurrentApp() // 当前应用
    if (!currentApp) { // 无选中
      set({ discovered: null }) // 清空树
      return // 结束
    }
    try {
      const data = await fetch( // 拉发现文件
        `${API}/discovered?app_name=${encodeURIComponent(currentApp.displayName)}` // 按 displayName
      ).then(res => res.json()) // 解析 JSON（平铺 [{file_path, hit_count}]）
      set({ discovered: buildTree(data) }) // 前端自建树后写入
    } catch {
      set({ discovered: null }) // 失败清空
    }
  },

  /**
   * 保存配置并尝试重启 daemon
   * @param {object} [newConfig] 要保存的配置，默认取 store.config
   * @returns {Promise<void>}
   * @api PUT /api/edit_monitor/config
   */
  saveConfigNow: async (newConfig) => {
    const payload = newConfig ?? get().config // 默认当前 config
    if (!payload) return // 无数据不写
    set({ saving: true }) // 进入保存中
    try {
      await fetch(`${API}/config`, { // 写配置
        method: 'PUT', // PUT
        headers: { 'Content-Type': 'application/json' }, // JSON
        body: JSON.stringify(payload), // 序列化
      })
      set({ config: payload, dirty: false }) // 同步内存并清 dirty
      await fetch(`/api/daemon/edit_monitor/restart`) // 重启服务（name=manifest.name）
      await new Promise(r => setTimeout(r, 2000)) // 等 2s
      const s = await fetch(`/api/daemon/edit_monitor/status`).then(res => res.json()) // 查状态
      if (s.status === 'stopped') await fetch(`/api/daemon/edit_monitor/start`) // 停了再启
    } catch (e) {
      console.error('save fail', e) // 保存失败
    } finally {
      set({ saving: false }) // 结束 saving
    }
  },

  /**
   * 切换应用 enabled，并重排列表后立即保存
   * @param {number} visibleIndex 可见列表下标
   * @returns {Promise<void>}
   */
  toggleApp: async (visibleIndex) => {
    const { config } = get() // 当前 config
    if (!config) return // 无配置
    const visibleApps = buildVisibleApps(config) // 可见列表
    const target = visibleApps[visibleIndex] // 目标 app
    if (!target) return // 无效下标
    const originalIndex = config.apps.indexOf(target) // 原数组下标
    if (originalIndex < 0) return // 找不到
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    const app = newConfig.apps[originalIndex] // 拷贝中的 app
    app.enabled = !app.enabled // 翻转开关
    if (app.enabled) { // 打开：摘出后插到 enabled 区
      newConfig.apps.splice(originalIndex, 1) // 先摘出
      const cnt = newConfig.apps.filter(a => !a.is_delete && a.enabled).length - 1 // 与原逻辑一致
      newConfig.apps.splice(cnt, 0, app) // 插入
    } else { // 关闭：摘出后插到 enabled 区之后
      newConfig.apps.splice(originalIndex, 1) // 先摘出
      const cnt = newConfig.apps.filter(a => !a.is_delete && a.enabled).length // 已开个数
      newConfig.apps.splice(cnt, 0, app) // 插入
    }
    await get().saveConfigNow(newConfig) // 立即保存
  },

  /**
   * 本地修改 allow_postfix（不写盘）
   * @param {string[]} list 新后缀列表
   * @returns {void}
   */
  updatePostfixLocal: (list) => {
    const { config } = get() // 当前 config
    const currentApp = get().getCurrentApp() // 当前 app
    if (!config || !currentApp) return // 缺数据
    const origIdx = config.apps.indexOf(currentApp) // 原下标
    if (origIdx < 0) return // 找不到
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    newConfig.apps[origIdx].allow_postfix = list // 改后缀
    set({ config: newConfig, dirty: true }) // 写回并 dirty
  },

  /**
   * 本地修改 fileignore（不写盘）
   * @param {string[]} list 新忽略规则
   * @returns {void}
   */
  updateFileignoreLocal: (list) => {
    const { config } = get() // 当前 config
    const currentApp = get().getCurrentApp() // 当前 app
    if (!config || !currentApp) return // 缺数据
    const origIdx = config.apps.indexOf(currentApp) // 原下标
    if (origIdx < 0) return // 找不到
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    newConfig.apps[origIdx].fileignore = list // 改忽略
    set({ config: newConfig, dirty: true }) // 写回并 dirty
  },

  /**
   * 确认添加忽略规则
   * @param {string} pattern 忽略模式
   * @returns {void}
   */
  confirmIgnore: (pattern) => {
    const { config } = get() // 当前 config
    const currentApp = get().getCurrentApp() // 当前 app
    if (!config || !currentApp) return // 缺数据
    const origIdx = config.apps.indexOf(currentApp) // 原下标
    if (origIdx < 0) return // 找不到
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    newConfig.apps[origIdx].fileignore = [...(currentApp.fileignore || []), pattern] // 追加规则
    set({ config: newConfig, dirty: true, popover: null }) // 写回、dirty、关弹层
  },

  /**
   * 确认「显示」：去掉后缀或去掉忽略规则
   * @param {string} pattern 模式
   * @param {'suffix'|'folder'} type 类型
   * @returns {void}
   */
  confirmShow: (pattern, type) => {
    const { config } = get() // 当前 config
    const currentApp = get().getCurrentApp() // 当前 app
    if (!config || !currentApp) return // 缺数据
    const origIdx = config.apps.indexOf(currentApp) // 原下标
    if (origIdx < 0) return // 找不到
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    if (type === 'suffix') { // 从 allow_postfix 移除
      newConfig.apps[origIdx].allow_postfix = (currentApp.allow_postfix || []).filter(p => p !== pattern) // 过滤
    } else { // 从 fileignore 移除
      newConfig.apps[origIdx].fileignore = (currentApp.fileignore || []).filter(p => p !== pattern) // 过滤
    }
    set({ config: newConfig, dirty: true, popover: null }) // 写回、dirty、关弹层
  },

  /**
   * 确认移除应用（is_delete=true）并立即保存
   * @returns {Promise<void>}
   */
  confirmAppDelete: async () => {
    const { config } = get() // 当前 config
    const currentApp = get().getCurrentApp() // 当前 app
    if (!config || !currentApp) return // 缺数据
    const origIdx = config.apps.indexOf(currentApp) // 原下标
    if (origIdx < 0) return // 找不到
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    newConfig.apps[origIdx].is_delete = true // 假删标记
    set({ selectedAppIndex: 0, appDeleteDialog: false }) // 切回第一项并关弹窗
    await get().saveConfigNow(newConfig) // 立即保存
  },

  /**
   * 打开「+ 添加应用」：扫本机 App 列表
   * @returns {Promise<void>}
   * @api GET /api/edit_monitor/mac_apps
   */
  openAddApp: async () => {
    const { config } = get() // 当前 config
    if (!config) return // 无配置
    const apps = await fetch(`${API}/mac_apps`).then(res => res.json()) // 扫 /Applications
    const existingNotDeleted = new Set( // 已存在且未删
      config.apps.filter(a => !a.is_delete && a.app_path).map(a => a.app_path) // 取 app_path
    )
    set({ // 写可添加列表并打开弹层
      macApps: apps.filter(a => !existingNotDeleted.has(a.exec_path)), // 过滤已有
      addAppPopover: true, // 打开
    })
  },

  /**
   * 从本机列表选中一个 App：恢复或进入后缀选择
   * @param {object} app mac_apps 项
   * @returns {Promise<void>}
   */
  selectAppForAdd: async (app) => {
    const { config } = get() // 当前 config
    if (!config) return // 无配置
    const isRestore = config.apps.some(a => a.app_path === app.exec_path && a.is_delete) // 是否恢复
    if (isRestore) { // 恢复已删除
      const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
      const target = newConfig.apps.find(a => a.app_path === app.exec_path && a.is_delete) // 找目标
      if (target) target.is_delete = false // 取消假删
      set({ addAppPopover: false }) // 关弹层
      await get().saveConfigNow(newConfig) // 立即保存
    } else { // 新应用 → 后缀弹窗
      set({ // 打开后缀选择
        suffixDialog: { app, isRestore: false }, // 弹窗数据
        suffixSelections: [], // 清空多选
        addAppPopover: false, // 关列表弹层
      })
    }
  },

  /**
   * 确认添加新应用（带后缀选择结果）
   * @returns {Promise<void>}
   */
  confirmAddApp: async () => {
    const { config, suffixDialog, suffixSelections } = get() // 取状态
    if (!config || !suffixDialog?.app) return // 缺数据
    const app = suffixDialog.app // 待添加 app
    const newConfig = JSON.parse(JSON.stringify(config)) // 深拷贝
    newConfig.apps.push({ // 追加新条目
      displayName: app.name, // 显示名
      app_path: app.exec_path, // 进程路径
      allow_postfix: suffixSelections, // 选中后缀
      fileignore: [], // 默认无忽略
      enabled: true, // 默认开启
      is_delete: false, // 未删除
    })
    set({ suffixDialog: null }) // 关后缀弹窗
    await get().saveConfigNow(newConfig) // 立即保存
  },
}))

export default useEditMonitorStore // 默认导出 store hook
