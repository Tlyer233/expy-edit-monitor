/**
 * 常用后缀分组常量
 * @description 添加应用时可选后缀分组（从原 FileTree.jsx POSTFIX_GROUPS 拆出）
 */

/** 添加应用时可选后缀分组 */
export const POSTFIX_GROUPS = [
  {
    label: '常用代码后缀', // 分组名
    options: ['.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.html', '.css', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.swift', '.kt', '.rb', '.php', '.sh', '.sql', '.yaml', '.yml', '.xml', '.toml'], // 选项
  },
  {
    label: '常用文档后缀', // 分组名
    options: ['.md', '.txt', '.markdown', '.rst', '.tex', '.csv'], // 选项
  },
  {
    label: 'Office 后缀', // 分组名
    options: ['.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt', '.pdf'], // 选项
  },
  {
    label: '配置/工程后缀', // 分组名
    options: ['.cfg', '.ini', '.env', '.properties', '.gradle', '.lock', '.gitignore'], // 选项
  },
]
