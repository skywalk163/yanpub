# 极快 (Jikuai) 贡献指南

## 适配器开发

极快适配器位于 `src/yanpub/adapters/jikuai/`，包含：

- `adapter.py` — 适配器实现，继承 `SubprocessAdapter`
- `adapter.yaml` — 语言元信息配置
- `keywords.json` — 关键字缓存列表
- `README.md` — 适配器文档
- `examples/` — 示例代码

## 本地开发

```bash
# 设置极快项目路径（或使用默认路径 G:\jikuai）
export JIKUAI_DIR=/path/to/jikuai

# 运行测试
python -m pytest tests/test_jikuai.py
```

## 添加关键字

编辑 `keywords.json` 或更新 `adapter.py` 中的 `_fallback_jikuai_keywords()`。

动态加载会从极快项目的 `src/jikuai/keywords.py` 读取 `ALL_KEYWORDS`。
