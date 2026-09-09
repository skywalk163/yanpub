# 光明 (Light) 适配器

## 语言信息

| 属性 | 值 |
|------|-----|
| 名称 | 光明 |
| ID | `light` |
| 版本 | 7.0.0 |
| 文件扩展名 | `.light` |
| 注释语法 | `#` |
| 后端类型 | Python 子进程 |

## 仓库

| 镜像 | URL |
|------|-----|
| 内网 | http://192.168.1.5:3000/skywalk/light |
| GitCode | https://gitcode.com/skywalk163/light |
| GitHub | https://github.com/skywalk163/light |

## CLI 用法

```bash
# 运行文件
python cli/light.py run hello.light

# 编译为 Python
python cli/light.py compile hello.light -o out.py

# 显示 AST
python cli/light.py ast hello.light

# 进入 REPL
python cli/light.py repl

# 语法检查
python cli/light.py check hello.light

# 包管理
python cli/light.py pkg init
python cli/light.py pkg build
python cli/light.py pkg run
```

## 示例

```light
# 光明编程语言示例
设甲为123
设乙为3加5
打印("变量声明：")
打印(甲)
打印(乙)

如果甲大于乙：
  打印("甲大于乙")
否则：
  打印("甲小于等于乙")

段落加法接收甲，乙：
  返回甲加乙

设和为加法(3，5)
打印("函数调用：")
打印(和)
```
