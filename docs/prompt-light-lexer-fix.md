# 光明 Lexer 修复任务

## 问题

以下代码报 `NameError: name '甲加乙' is not defined`：

```
设甲为10
设乙为20
打印(甲加乙)
```

`甲加乙` 应被分词为 `甲(IDENTIFIER)` + `加(KEYWORD/运算符)` + `乙(IDENTIFIER)`，但实际被识别为单个标识符 `甲加乙`。

同样影响 `3加5` 以外的所有"变量+运算符+变量"无空格写法，如 `甲乘乙`、`甲减乙` 等。

## 根因

文件：`src/lexer.py`，函数 `_tokenize_chinese_sequence`

三层分词流程中，`_scan_user_definitions` 预扫描会把 `甲` 收集为用户定义变量。然后在 `_tokenize_chinese_sequence` 中处理 `甲加乙` 时：

1. `甲` 被识别为用户定义前缀，从 `甲加乙` 中拆出
2. 剩余部分 `加乙` 的 `加` 是单字运算符，在 `_compound_safe` 集合中
3. `加` 处于词首位置（相对于剩余部分），`compound_safe` 逻辑判断"动词在词首且后面有内容时跳过"
4. 结果 `加乙` 被当作一个完整标识符，不再拆分

核心问题：用户定义前缀拆分后，剩余部分以运算符动词开头时，不应该拆分前缀——应该让整个标识符走正常的关键字嵌入扫描流程，由嵌入扫描正确识别中间的运算符。

## 修复

在 `_tokenize_chinese_sequence` 函数中，找到用户定义前缀拆分的逻辑（`prefix_matched` 判断处）。

当前代码大致结构：

```python
if prefix_matched:
    remaining = full_identifier[len(prefix_matched):]
    if len(remaining) == 1 and remaining in _compound_safe:
        prefix_matched = None
    else:
        # 正常拆分...
```

在 `compound_safe` 检查之后、`else` 之前，新增一个分支：

```python
if prefix_matched:
    remaining = full_identifier[len(prefix_matched):]
    if len(remaining) == 1 and remaining in _compound_safe:
        prefix_matched = None
    elif remaining and remaining[0] in OPERATOR_VERBS:
        # 剩余部分以运算符动词开头（如"甲加乙"拆出"甲"后剩"加乙"）
        # 不拆分，让整个标识符走正常流程，嵌入扫描会正确识别运算符
        prefix_matched = None
    else:
        # 正常拆分...
```

`OPERATOR_VERBS` 已在文件顶部定义（包含 `加`、`减`、`乘`、`除`、`模`、`幂`、`大于`、`小于`、`等于` 等）。

## 验证

修复后分词结果应为：

```
设甲为10          → 设(KW) 甲(ID) 为(KW) 10(NUM)
设乙为20          → 设(KW) 乙(ID) 为(KW) 20(NUM)
打印(甲加乙)      → 打印(KW) ( LP 甲(ID) 加(KW) 乙(ID) ) RP
```

关键确认：
- `甲加乙` → `甲` + `加` + `乙`（三 token，运算符正确拆出）
- `加法` 仍为完整标识符（`加法` 不在 `OPERATOR_VERBS` 中，不受影响）
- `3加5` 仍正确分词（数字→中文运算符→数字，走另一条路径不受影响）

测试命令：

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from lexer import Lexer
lex = Lexer()
tokens = lex.tokenize('设甲为10\n设乙为20\n打印(甲加乙)')
for t in tokens:
    print(f'{t.type.name:15s} {t.value!r}')
"
```

预期输出中 `甲加乙` 那行应为三个 token：`甲(IDENTIFIER)`、`加(KEYWORD)`、`乙(IDENTIFIER)`。
