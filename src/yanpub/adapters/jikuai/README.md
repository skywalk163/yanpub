# 极快 (Jikuai) 适配器

## 语言信息

| 属性 | 值 |
|------|-----|
| 名称 | 极快 |
| ID | `jikuai` |
| 版本 | 0.20.0 |
| 文件扩展名 | `.快`, `.jk` |
| 注释语法 | `--` |
| 后端类型 | Python 子进程 |

## 仓库

| 镜像 | URL |
|------|-----|
| 内网 | http://192.168.1.5:3000/skywalk/jikuai |
| GitCode | https://gitcode.com/skywalk163/jikuai |
| GitHub | https://github.com/skywalk163/jikuai |

## CLI 用法

```bash
# 运行文件
python -m jikuai.main hello.jk

# 进入 REPL
python -m jikuai.main

# 包管理
python -m jikuai.main 包 初始化
python -m jikuai.main 包 装依赖

# 块生态
python -m jikuai.main 块 列表
```

## 示例

```jikuai
-- 极快语言示例
打印 "你好，世界！"。

定义 甲 为 42。
定义 乙 为 甲 乘 2。
打印(乙)。

函数 求和 接收 甲, 乙：
  返回 甲 加 乙。

定义 结果 为 求和(3, 5)。
打印(结果)。
```
