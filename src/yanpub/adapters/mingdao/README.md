# 明道 (Mingdao) 适配器

> 基于 Racket 的主谓式中文编程语言

## 基本信息

| 属性 | 值 |
|------|-----|
| 语言 ID | `mingdao` |
| 版本 | 0.6.0 |
| 文件扩展名 | `.道`、`.mingdao`、`.rkt` |
| 注释语法 | `;;` |
| REPL 提示符 | `明道> ` |

## 安装

明道基于 Racket 实现，需要先安装 Racket 运行时：

```bash
# 安装 Racket（https://racket-lang.org/）
# Windows: 下载安装包或使用 scoop install racket

# 运行明道文件
racket -S <项目路径> <file>

# 进入 REPL
racket mingdao/repl.rkt
```

文件必须以 `#lang mingdao` 开头声明语言。

## 语法示例

### Hello World

```mingdao
#lang mingdao
42, 打印

定义 甲 就是 42
定义 乙 就是 甲 乘以 2
乙, 打印

定义 求和 就是函 甲, 乙：
    返回 甲 加上 乙

定义 结果 就是 求和, 3, 5
结果, 打印
```

### 变量与运算

```mingdao
#lang mingdao
42, 打印

定义 甲 就是 42
定义 乙 就是 甲 乘以 2
乙, 打印

定义 求和 就是函 甲, 乙：
    返回 甲 加上 乙

定义 结果 就是 求和, 3, 5
结果, 打印
```

### 斐波那契数列

```mingdao
#lang mingdao
定义 斐波那契 就是函 n：
    如果 n 小于 2 那么：
        返回 n
    否则：
        返回 (斐波那契, n 减去 1) 加上 (斐波那契, n 减去 2)

对于 i 从 0 到 9：
    (拼接, "fib(", i, ") = ", 斐波那契, i), 打印
```

## 关键字

定义、常量、就是、就是函、定义宏、就是宏、如果、那么、否则、否则若、对于、从、到、对于每个、当满足、跳出、继续、返回、列表、元组

## 已知限制

- 需要系统安装 Racket 运行时，依赖较重
- 无内置 eval 命令，代码片段执行需自动添加 `#lang mingdao` 头部
- 不支持包管理器和 WASM 执行
- SVO（主谓宾）调用风格需要适应

## 贡献

欢迎贡献示例代码和改进！请遵循项目的[示例贡献指南](../../docs/CONTRIBUTING.md)。
