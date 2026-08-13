# 极快 RuntimeWarning 修复任务

## 问题

用 `python -m jikuai.main` 运行时输出警告：

```
<frozen runpy>:128: RuntimeWarning: 'jikuai.main' found in sys.modules after import of package 'jikuai', but prior to execution of 'jikuai.main'; this may result in unpredictable behaviour
```

不影响功能，但每次运行都会出现，干扰用户体验。

## 根因

`src/jikuai/__init__.py` 第 16 行：

```python
from .main import main, repl, run_file, run_source
```

当 `python -m jikuai.main` 执行时，Python 先导入 `jikuai` 包（触发 `__init__.py`），此时 `main` 模块已被导入到 `sys.modules`。然后 runpy 尝试执行 `jikuai.main` 作为 `__main__`，发现它已在 `sys.modules` 中，于是发出 RuntimeWarning。

## 修复方案

在 `src/jikuai/` 目录下新增 `__main__.py`：

```python
# -*- coding: utf-8 -*-
"""python -m jikuai 入口，避免 __init__.py 提前导入 main 导致的 RuntimeWarning。"""

from jikuai.main import main

if __name__ == "__main__":
    main()
```

然后 yanpub 侧可以将启动命令从 `python -m jikuai.main` 改为 `python -m jikuai`，不再触发 `__init__.py` → `main` 的提前导入链。

## 验证

修复后 `python -m jikuai` 应无 RuntimeWarning：

```bash
cd src && python -m jikuai ../examples/hello.jk
```

预期输出：

```
你好，世界！
```

无 `<frozen runpy>:128: RuntimeWarning` 行。
