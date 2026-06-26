# 趣言 (Traeyan) 适配器

> THULAC 分词驱动的动词吞噬式中文编程语言

## 基本信息

| 属性 | 值 |
|------|-----|
| 语言 ID | `traeyan` |
| 版本 | 0.8.0 |
| 文件扩展名 | `.行`、`.yan` |
| 注释语法 | `#` |
| REPL 提示符 | `>>> ` |

## 安装

趣言基于 Python 实现，特色为 THULAC 分词和动词吞噬解析：

```bash
# 确保已安装 Python 3.8+
# 需要安装 THULAC 分词库
pip install thulac

# 运行文件
python -m traeyan.main <file>

# 进入 REPL
python -m traeyan.main
```

## 语法示例

### Hello World

```traeyan
印"你好，世界！"。

定甲等于42。
定乙等于加甲 2。
印乙。

定mysum等于函a b：
  返加a b。
。

定result等于mysum 3 5。
印result。
```

### 变量与运算

```traeyan
印"你好，世界！"。

定甲等于42。
定乙等于加甲 2。
印乙。

定mysum等于函a b：
  返加a b。
。

定result等于mysum 3 5。
印result。

# 简单循环
定i等于0。
当i小5：
  印"计数："加i。
  定i等于加i 1。
结束
```

### 斐波那契数列

```traeyan
# 循环与函数演示

定i等于0。
当i小等于5：
  印"第"加i加"次循环"。
  定i等于加i 1。
结束。

定mysum等于函x y：
  返加x y。
。

印"3 + 5 = "。
印mysum 3 5。
```

## 关键字

定、设、函、若、则、否则、否则若、当、每、遍历、重复、从、到、真、假、空、尝试、捕获、最终、抛出

## 已知限制

- 无内置 eval 命令，代码片段执行依赖临时文件回退机制
- 动词吞噬解析机制对部分语法结构有特殊限制
- 依赖 THULAC 分词库，安装体积较大
- 不支持包管理器和 WASM 执行

## 贡献

欢迎贡献示例代码和改进！请遵循项目的[示例贡献指南](../../docs/CONTRIBUTING.md)。
