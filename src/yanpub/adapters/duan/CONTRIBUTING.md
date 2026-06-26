# 贡献指南

感谢你对 段言 适配器的关注！

## 如何贡献

### 报告问题

请在项目 [Issue 页面](https://github.com/skywalk163/yanpub/issues) 提交 bug 报告，包含：
- 复现步骤
- 期望行为与实际行为
- 运行环境信息

### 贡献示例代码

1. 在 `examples/` 目录下创建新的示例文件
2. 添加 YAML front matter 元数据（标题、难度、标签、作者）
3. 运行验证：`yanpub validate-examples duan`
4. 提交 PR

### 改进适配器

1. Fork 项目仓库
2. 创建功能分支
3. 修改 `adapter.py` 或相关文件
4. 运行测试：`pytest tests/ -q`
5. 提交 PR

## 开发规范

- 保持与 LanguageAdapter 协议的兼容性
- 新增功能需添加对应测试
- 遵循项目的代码风格（ruff check）

## 示例验证

使用 `yanpub contribute duan` 命令交互式贡献示例，或使用 `yanpub validate-examples duan` 验证现有示例。
