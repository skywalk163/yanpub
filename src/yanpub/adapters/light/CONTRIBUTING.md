# 光明 (Light) 贡献指南

## 适配器开发

光明适配器位于 `src/yanpub/adapters/light/`，包含：

- `adapter.py` — 适配器实现，继承 `SubprocessAdapter`
- `adapter.yaml` — 语言元信息配置
- `keywords.json` — 关键字缓存列表
- `README.md` — 适配器文档
- `examples/` — 示例代码

## 本地开发

```bash
# 设置光明项目路径（或使用默认路径 G:\github\light）
export LIGHT_DIR=/path/to/light

# 运行测试
python -m pytest tests/test_light.py
```

## 添加关键字

编辑 `keywords.json` 或更新 `adapter.py` 中的 `_fallback_light_keywords()`。

动态加载会从光明项目的 `src/keywords.py` 读取 `ALL_KEYWORDS`。

## 光明语言特性

- 五层分层语法架构（L0-L4）
- L0 核心字表 30 字冻结
- 动词元数驱动解析
- 支持 ANTLR 和 SRC 双后端
- 类型推断与空安全
- 模块系统与 FFI
