"""语言语法对比矩阵 — 同一概念在不同语言中的代码写法对比

核心设计：定义一组"语法概念"，每种语言提供该概念的实际代码片段，
生成"概念 × 语言"的矩阵，让用户直观看到各语言的语法差异。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from yanpub.core.adapter.registry import get_registry


# ---- 语法概念定义 ----


@dataclass
class SyntaxConcept:
    """一个语法概念"""

    id: str  # 概念标识，如 "var_declare"
    title: str  # 显示标题，如 "变量声明"
    category: str  # 分类：基础/函数/控制流/数据结构/面向对象/异常/模块
    description: str  # 简短描述
    difficulty: str = "入门"  # 难度


@dataclass
class SnippetEntry:
    """某个语言在某个概念下的代码片段"""

    lang_id: str
    code: str
    note: str = ""  # 额外说明（如"中文运算符"、"前缀调用"等）


# ---- 预定义的语法概念（15个核心概念） ----

CONCEPTS: list[SyntaxConcept] = [
    SyntaxConcept("hello", "你好世界", "基础", "最简单的程序", "入门"),
    SyntaxConcept("var_declare", "变量声明", "基础", "声明并赋值一个变量", "入门"),
    SyntaxConcept("var_assign", "变量赋值/修改", "基础", "修改变量的值", "入门"),
    SyntaxConcept("func_def", "函数定义", "函数", "定义一个带参数和返回值的函数", "入门"),
    SyntaxConcept("func_call", "函数调用", "函数", "调用函数并使用返回值", "入门"),
    SyntaxConcept("if_else", "条件语句", "控制流", "if-else 条件判断", "入门"),
    SyntaxConcept("while_loop", "while 循环", "控制流", "当型循环", "简单"),
    SyntaxConcept("for_loop", "遍历循环", "控制流", "遍历列表/范围", "简单"),
    SyntaxConcept("list_ops", "列表操作", "数据结构", "创建列表、访问元素", "简单"),
    SyntaxConcept("dict_ops", "字典操作", "数据结构", "创建字典、存取键值", "中等"),
    SyntaxConcept("class_def", "类定义", "面向对象", "定义类、属性、方法", "中等"),
    SyntaxConcept("try_catch", "异常处理", "异常", "try-catch 捕获异常", "中等"),
    SyntaxConcept("import_mod", "模块导入", "模块", "导入外部模块", "简单"),
    SyntaxConcept("recursion", "递归函数", "函数", "递归调用自身", "中等"),
    SyntaxConcept("higher_order", "高阶函数", "函数", "map/filter/reduce 风格", "困难"),
]


# ---- 各语言的代码片段 ----
# 每个概念下，每种语言提供其实际写法

SNIPPETS: dict[str, dict[str, SnippetEntry]] = {
    # === 你好世界 ===
    "hello": {
        "duan": SnippetEntry("duan", '打印("你好，世界！")。', "中文句号结束"),
        "yan": SnippetEntry("yan", '打印("你好，世界！")', "前缀调用风格"),
        "moyan": SnippetEntry("moyan", '打印 "你好，世界！"。', "前缀调用 + 中文句号"),
        "mingdao": SnippetEntry("mingdao", '打印 "你好，世界！"', "主谓式，无括号"),
        "zhixing": SnippetEntry("zhixing", '打印("你好，世界！")', "管道式风格"),
        "xinyu": SnippetEntry("xinyu", '打印("你好，世界！")', "C 风格语法"),
        "traeyan": SnippetEntry("traeyan", '印"你好，世界！"。', "无括号，动词吞噬"),
        "hanyu": SnippetEntry("hanyu", '打印("你好，世界！")', "C 风格语法"),
        "yanlv": SnippetEntry("yanlv", '输出("你好，世界！")', "用「输出」而非「打印」"),
        "yanzhi": SnippetEntry("yanzhi", '打印("你好，世界！")', "C 风格语法"),
        "hua": SnippetEntry("hua", '输出 "你好，世界！"', "无括号输出，空格分隔"),
    },
    # === 变量声明 ===
    "var_declare": {
        "duan": SnippetEntry("duan", "设甲为四十二。", "「设…为…」统一格式"),
        "yan": SnippetEntry("yan", "定义 甲 = 42", "定义 + 等号赋值"),
        "moyan": SnippetEntry("moyan", "定义 甲 = 42。", "定义 + 等号赋值 + 中文句号"),
        "mingdao": SnippetEntry("mingdao", "定义 甲 = 42", "定义 + 等号赋值"),
        "zhixing": SnippetEntry("zhixing", "定 甲 = 42", "「定」缩写形式"),
        "xinyu": SnippetEntry("xinyu", "定 甲 = 42", "「定」缩写形式"),
        "traeyan": SnippetEntry("traeyan", "定甲等于42。", "无空格，句号结束"),
        "hanyu": SnippetEntry("hanyu", "定义 甲 = 42", "定义 + 等号赋值"),
        "yanlv": SnippetEntry("yanlv", "定 甲 = 42", "「定」缩写形式"),
        "yanzhi": SnippetEntry("yanzhi", "定义 甲 = 42", "定义 + 等号赋值"),
        "hua": SnippetEntry("hua", "变量甲 为 42", "「变量…为…」声明"),
    },
    "var_assign": {
        "duan": SnippetEntry("duan", "设甲为甲加一。", "重新设值（中文运算符）"),
        "yan": SnippetEntry("yan", "赋值 甲 = 甲 + 1", "显式「赋值」关键字"),
        "moyan": SnippetEntry("moyan", "赋值 甲 = 相加 甲 1。", "赋值 + 前缀运算 + 中文句号"),
        "mingdao": SnippetEntry("mingdao", "赋值 甲 = 甲 + 1", "显式「赋值」关键字"),
        "zhixing": SnippetEntry("zhixing", "甲 = 甲 + 1", "直接赋值"),
        "xinyu": SnippetEntry("xinyu", "甲 = 甲 + 1", "直接赋值"),
        "traeyan": SnippetEntry("traeyan", "甲加等于1。", "复合赋值运算符"),
        "hanyu": SnippetEntry("hanyu", "为 甲 = 甲 加 1", "「为」赋值 + 中文运算"),
        "yanlv": SnippetEntry("yanlv", "设置 甲 = 甲 + 1", "「设置」关键字"),
        "yanzhi": SnippetEntry("yanzhi", "赋值 甲 = 甲 + 1", "显式「赋值」关键字"),
        "hua": SnippetEntry("hua", "甲 += 1", "复合赋值运算符"),
    },
    # === 函数定义 ===
    "func_def": {
        "duan": SnippetEntry(
            "duan", "段落 求和 参数 甲 乙\n  返回 甲 加 乙。\n结束", "「段落…参数…结束」结构"
        ),
        "yan": SnippetEntry("yan", "定义 求和 = 函数 甲 乙 那么 相加 甲 乙", "前缀调用 + 内联函数"),
        "moyan": SnippetEntry("moyan", "定义 求和 = 函数 甲 乙 那么 相加 甲 乙。", "前缀调用 + 内联函数 + 中文句号"),
        "mingdao": SnippetEntry("mingdao", "就是函 求和 (甲 乙) (+ 甲 乙)", "Lisp 风格前缀表达式"),
        "zhixing": SnippetEntry(
            "zhixing", "函 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "「函」缩写 + C 风格"
        ),
        "xinyu": SnippetEntry("xinyu", "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "C 风格花括号"),
        "traeyan": SnippetEntry(
            "traeyan", "定求和等于函 甲 乙：\n  返回 甲加乙。\n结束", "无括号函数定义"
        ),
        "hanyu": SnippetEntry("hanyu", "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "C 风格花括号"),
        "yanlv": SnippetEntry("yanlv", "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "C 风格花括号"),
        "yanzhi": SnippetEntry("yanzhi", "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "C 风格花括号"),
        "hua": SnippetEntry("hua", "函数 求和\n  参数 甲 为 整数\n  参数 乙 为 整数\n  返回 甲 + 乙", "函数…参数…为类型…返回 + 缩进块"),
    },
    "func_call": {
        "duan": SnippetEntry("duan", "设结果为 求和(三, 五)。", "括号调用 + 中文运算"),
        "yan": SnippetEntry("yan", "定义 结果 = 求和 3 5", "空格分隔参数（前缀风格）"),
        "moyan": SnippetEntry("moyan", "定义 结果 = 求和 3 5。", "空格分隔参数（前缀风格）+ 中文句号"),
        "mingdao": SnippetEntry("mingdao", "定义 结果 = 求和(3, 5)", "括号调用"),
        "zhixing": SnippetEntry("zhixing", "定 结果 = 求和(3, 5)", "括号调用"),
        "xinyu": SnippetEntry("xinyu", "定 结果 = 求和(3, 5)", "括号调用"),
        "traeyan": SnippetEntry("traeyan", "定结果等于求和(3, 5)。", "括号调用 + 句号"),
        "hanyu": SnippetEntry("hanyu", "定义 结果 = 求和(3, 5)", "括号调用"),
        "yanlv": SnippetEntry("yanlv", "定 结果 = 求和(3, 5)", "括号调用"),
        "yanzhi": SnippetEntry("yanzhi", "定义 结果 = 求和(3, 5)", "括号调用"),
        "hua": SnippetEntry("hua", "变量结果 为 (求和 3 5)", "无括号调用 + 空格分隔参数"),
    },
    "if_else": {
        "duan": SnippetEntry(
            "duan",
            '如果 甲 大于 乙 那么：\n  打印("甲大")。\n否则：\n  打印("乙大")。\n结束',
            "如果…那么…否则…结束",
        ),
        "yan": SnippetEntry(
            "yan",
            '如果 甲 大于 乙 那么\n  打印("甲大")\n否则\n  打印("乙大")',
            "如果…那么…否则",
        ),
        "moyan": SnippetEntry(
            "moyan",
            '如果 大于 甲 乙 那么 打印 "甲大"。否则 打印 "乙大"。',
            "前缀条件 + 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            '如果 (> 甲 乙) 那么 打印 "甲大" 否则 打印 "乙大"',
            "Lisp 风格条件",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            '若 甲 > 乙 则 {\n  打印("甲大")\n} 否则 {\n  打印("乙大")\n}',
            "若…则…否则",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            '如果 甲 > 乙 那么 {\n  打印("甲大")\n} 否则 {\n  打印("乙大")\n}',
            "如果…那么…否则",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            '若甲大乙：\n  印"甲大"。\n否则：\n  印"乙大"。\n结束',
            "无空格条件",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            '如果 甲 大于 乙 那么 {\n  打印("甲大")\n} 否则 {\n  打印("乙大")\n}',
            "中文运算符",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            '如果 甲 > 乙 那么 {\n  打印("甲大")\n} 否则 {\n  打印("乙大")\n}',
            "如果…那么…否则",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            '如果 甲 大于 乙 那么 {\n  打印("甲大")\n} 否则 {\n  打印("乙大")\n}',
            "中文运算符",
        ),
        "hua": SnippetEntry(
            "hua",
            '如果 甲 大于 乙\n  输出 "甲大"\n否则\n  输出 "乙大"',
            "如果…否则 + 缩进块 + 中文比较",
        ),
    },
    # === while 循环 ===
    "while_loop": {
        "duan": SnippetEntry(
            "duan",
            "当 甲 小于 十：\n  打印(甲)。\n  设甲为甲加一。\n结束",
            "当…结束",
        ),
        "yan": SnippetEntry(
            "yan",
            "每当 甲 小于 10 时候\n  打印(甲)\n  赋值 甲 = 甲 + 1",
            "每当…时候",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "当 小于 甲 10 时候 打印 甲。赋值 甲 = 相加 甲 1。",
            "当…时候 + 前缀运算 + 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "做当满足 (> 10 甲) 打印 甲\n  赋值 甲 = 甲 + 1",
            "Lisp 风格循环",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "当 甲 < 10 {\n  打印(甲)\n  甲 = 甲 + 1\n}",
            "当 + 花括号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "当满足 甲 < 10 {\n  打印(甲)\n  甲 = 甲 + 1\n}",
            "当满足 + 花括号",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "当甲小10：\n  印甲。\n  甲加等于1。\n结束",
            "无空格条件",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            "当满 甲 < 10 {\n  打印(甲)\n  甲 = 甲 加 1\n}",
            "当满 + 花括号",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "当 甲 < 10 {\n  打印(甲)\n  甲 = 甲 + 1\n}",
            "当 + 花括号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "循环当 甲 < 10 {\n  打印(甲)\n  甲 = 甲 + 1\n}",
            "循环当 + 花括号",
        ),
        "hua": SnippetEntry(
            "hua",
            "当 甲 小于 10 循环\n  输出 甲\n  甲 += 1",
            "当…循环 + 缩进块",
        ),
    },
    # === 遍历循环 ===
    "for_loop": {
        "duan": SnippetEntry(
            "duan",
            "遍历 甲 于 列表：\n  打印(甲)。\n结束",
            "遍历…于…结束",
        ),
        "yan": SnippetEntry(
            "yan",
            "遍历 甲 于中 列表\n  打印(甲)",
            "遍历…于中",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "列表，每个 打印。",
            "管道操作 + 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "对于每个 甲 于中 列表\n  打印 甲",
            "对于每个…于中",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "遍历 甲 于 列表 {\n  打印(甲)\n}",
            "遍历…于 + 花括号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "遍历 甲 于中 列表 {\n  打印(甲)\n}",
            "遍历…于中 + 花括号",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "每甲于列表：\n  印甲。\n结束",
            "每…于…结束",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            "对于 甲 于中 列表 {\n  打印(甲)\n}",
            "对于…于中 + 花括号",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "遍历 每个 甲 于 列表 {\n  打印(甲)\n}",
            "遍历每个…于 + 花括号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "遍历 甲 于中 列表 {\n  打印(甲)\n}",
            "遍历…于中 + 花括号",
        ),
        "hua": SnippetEntry(
            "hua",
            "对于 值 在 列表\n  输出 值",
            "对于…在 + 缩进块",
        ),
    },
    # === 列表操作 ===
    "list_ops": {
        "duan": SnippetEntry(
            "duan",
            "设甲为 [三, 五, 八]。\n设乙为 甲[零]。\n设丙为 列表长度(甲)。",
            "方括号 + 中文索引",
        ),
        "yan": SnippetEntry(
            "yan",
            "定义 甲 = [3, 5, 8]\n定义 乙 = 甲[0]\n定义 丙 = 长度 甲",
            "前缀调用「长度」",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "定义 甲 = 列表 3 5 8。\n定义 乙 = 索引 甲 0。\n定义 丙 = 长度 甲。",
            "前缀调用「列表」「索引」「长度」+ 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "定义 甲 = 列表(3, 5, 8)\n定义 乙 = 索引 甲 0\n定义 丙 = 长度 甲",
            "Lisp 风格「索引」函数",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "定 甲 = [3, 5, 8]\n定 乙 = 甲[0]\n定 丙 = 列表长度(甲)",
            "C 风格",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "定 甲 = [3, 5, 8]\n定 乙 = 甲[0]\n定 丙 = 长度(甲)",
            "C 风格",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "定甲等于列(3, 5, 8)。\n定乙等于甲[0]。\n定丙等于长度(甲)。",
            "「列」+ 句号",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            "定义 甲 = [3, 5, 8]\n定义 乙 = 甲[0]\n定义 丙 = 长度(甲)",
            "C 风格",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "定 甲 = [3, 5, 8]\n定 乙 = 甲[0]\n定 丙 = 长度(甲)",
            "C 风格",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "定义 甲 = [3, 5, 8]\n定义 乙 = 甲[0]\n定义 丙 = 长度(甲)",
            "C 风格",
        ),
        "hua": SnippetEntry(
            "hua",
            "变量甲 为 [3, 5, 8]\n变量乙 为 (索引 甲 0)\n变量丙 为 (大小 甲)",
            "变量…为 + 内置函数无括号",
        ),
    },
    # === 字典操作 ===
    "dict_ops": {
        "duan": SnippetEntry(
            "duan",
            '设甲为 字典()。\n字典设置(甲, "名", "张三")。\n设乙为 字典获取(甲, "名")。',
            "函数式字典操作",
        ),
        "yan": SnippetEntry(
            "yan",
            '定义 甲 = 字典()\n设置 甲 "名" "张三"\n定义 乙 = 获取 甲 "名"',
            "前缀调用风格",
        ),
        "moyan": SnippetEntry(
            "moyan",
            '定义 甲 = 字典。\n设置 甲 "名" "张三"。\n定义 乙 = 获取 甲 "名"。',
            "前缀调用 + 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            '定义 甲 = 字典\n定义 乙 = 索引 甲 "名"',
            "Lisp 风格",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            '定 甲 = {"名": "张三"}\n定 乙 = 甲["名"]',
            "花括号字面量",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            '定 甲 = {"名": "张三"}\n定 乙 = 甲["名"]',
            "花括号字面量",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            '定甲等于字典()。\n甲["名"]等于"张三"。\n定乙等于甲["名"]。',
            "函数式 + 句号",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            '定义 甲 = 字典()\n调用 甲 设置 "名" "张三"\n定义 乙 = 甲["名"]',
            "「调用」风格",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            '定 甲 = {"名": "张三"}\n定 乙 = 甲["名"]',
            "花括号字面量",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            '定义 甲 = {"名": "张三"}\n定义 乙 = 甲["名"]',
            "花括号字面量",
        ),
        "hua": SnippetEntry(
            "hua",
            '变量甲 为 ["名" 映射到 "张三"]\n变量乙 为 (获取 甲 "名")',
            "「映射到」字面量 + 获取",
        ),
    },
    "class_def": {
        "duan": SnippetEntry(
            "duan",
            '类 动物。\n  属性 名字。\n  构造 参数 名字。\n    己名字 为 名字。\n  结束\n  段落 说话 参数\n    打印(己名字 + "叫了一声")。\n  结束\n结束',
            "类…属性…构造…结束",
        ),
        "yan": SnippetEntry(
            "yan",
            "# 言暂不支持类定义",
            "暂不支持",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "-- 墨言暂不支持类定义",
            "暂不支持",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "# 明道暂不支持类定义",
            "暂不支持",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "# 知行暂不支持类定义",
            "暂不支持",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "# 心语暂不支持类定义",
            "暂不支持",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "# 趣言暂不支持类定义",
            "暂不支持",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            '结构 动物\n  名字\n  方法 说话\n    打印(名字 + "叫了一声")\n',
            "「结构」关键字",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "# 言律暂不支持类定义",
            "暂不支持",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "# 言知暂不支持类定义",
            "暂不支持",
        ),
        "hua": SnippetEntry(
            "hua",
            '类 动物\n  方法 说话\n    输出(自己.名字 + "叫了一声")',
            "类…方法… + 缩进块",
        ),
    },
    "try_catch": {
        "duan": SnippetEntry(
            "duan",
            "尝试：\n  设甲为 危险操作()。\n捕获 错误：\n  打印(错误)。\n结束",
            "尝试…捕获…结束",
        ),
        "yan": SnippetEntry(
            "yan",
            "试\n  定义 甲 = 危险操作()\n捕获 错误\n  打印(错误)",
            "试…捕获",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "试 危险操作。捕获 错误 打印 错误。",
            "试…捕获 + 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "# 明道暂不支持异常处理",
            "暂不支持",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "尝试 {\n  定 甲 = 危险操作()\n} 捕获 错误 {\n  打印(错误)\n}",
            "尝试…捕获 + 花括号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "尝试 {\n  定 甲 = 危险操作()\n} 捕获 错误 {\n  打印(错误)\n}",
            "尝试…捕获 + 花括号",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "尝试：\n  定甲等于危险操作()。\n捕获错误：\n  印错误。\n结束",
            "尝试…捕获…结束",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            "尝试 {\n  定义 甲 = 危险操作()\n} 捕获 错误 {\n  打印(错误)\n}",
            "尝试…捕获 + 花括号",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "尝试 {\n  定 甲 = 危险操作()\n} 捕获 错误 {\n  打印(错误)\n}",
            "尝试…捕获 + 花括号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "尝试 {\n  定义 甲 = 危险操作()\n} 捕获 错误 {\n  打印(错误)\n}",
            "尝试…捕获 + 花括号",
        ),
        "hua": SnippetEntry(
            "hua",
            "尝试\n  变量甲 为 危险操作()\n捕获 错误\n  输出 错误\n最终\n  输出 \"完成\"",
            "尝试…捕获…最终 + 缩进块",
        ),
    },
    "import_mod": {
        "duan": SnippetEntry("duan", "导入《数学》。", "书名号模块名"),
        "yan": SnippetEntry("yan", "导入 数学", "空格分隔"),
        "moyan": SnippetEntry("moyan", "导入 数学", "空格分隔"),
        "mingdao": SnippetEntry("mingdao", "导入 数学", "空格分隔"),
        "zhixing": SnippetEntry("zhixing", "导入 数学", "空格分隔"),
        "xinyu": SnippetEntry("xinyu", "导入 数学", "空格分隔"),
        "traeyan": SnippetEntry("traeyan", "导入 数学", "空格分隔"),
        "hanyu": SnippetEntry("hanyu", "导入 数学", "空格分隔"),
        "yanlv": SnippetEntry("yanlv", "导入 数学", "空格分隔"),
        "yanzhi": SnippetEntry("yanzhi", "导入 数学", "空格分隔"),
        "hua": SnippetEntry("hua", "导入 从 数学库 中的 [平方根]", "选择性导入 + 从…中的"),
    },
    "recursion": {
        "duan": SnippetEntry(
            "duan",
            "段落 斐波那契 参数 甲\n  如果 甲 小于 二 那么：\n    返回 甲。\n  结束\n  返回 斐波那契(甲减一) 加 斐波那契(甲减二)。\n结束",
            "段落递归 + 中文运算",
        ),
        "yan": SnippetEntry(
            "yan",
            "定义 斐波那契 = 函数 甲\n  如果 甲 小于 2 那么 返回 甲\n  返回 相加 (斐波那契 甲 减 1) (斐波那契 甲 减 2)",
            "前缀调用递归",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "定义 斐波那契 = 函数 甲 那么 如果 小于 甲 2 那么 甲 否则 相加 (斐波那契 (相减 甲 1)) (斐波那契 (相减 甲 2))。",
            "前缀递归 + 中文句号",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "就是函 斐波那契 (甲)\n  如果 (< 甲 2) 那么 甲\n  否则 (+ (斐波那契 (- 甲 1)) (斐波那契 (- 甲 2)))",
            "Lisp 风格递归",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "函 斐波那契(甲) {\n  若 甲 < 2 则 返回 甲\n  返回 斐波那契(甲-1) + 斐波那契(甲-2)\n}",
            "若…则递归",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "函数 斐波那契(甲) {\n  如果 甲 < 2 那么 返回 甲\n  返回 斐波那契(甲-1) + 斐波那契(甲-2)\n}",
            "C 风格递归",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "定斐波那契等于函 甲：\n  若甲小2：返回甲。\n  返回斐波那契(甲减1)加斐波那契(甲减2)。\n结束",
            "无空格递归",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            "函数 斐波那契(甲) {\n  如果 甲 小于 2 那么 返回 甲\n  返回 斐波那契(甲 减 1) 加 斐波那契(甲 减 2)\n}",
            "中文运算递归",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "函数 斐波那契(甲) {\n  如果 甲 < 2 那么 返回 甲\n  返回 斐波那契(甲-1) + 斐波那契(甲-2)\n}",
            "C 风格递归",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "函数 斐波那契(甲) {\n  如果 甲 小于 2 那么 返回 甲\n  返回 斐波那契(甲-1) + 斐波那契(甲-2)\n}",
            "中文运算递归",
        ),
        "hua": SnippetEntry(
            "hua",
            "函数 斐波那契\n  参数 甲 为 整数\n  如果 甲 小于等于 1\n    返回 1\n  返回 甲 * (斐波那契 (甲 - 1))",
            "函数递归 + 缩进块",
        ),
    },
    # === 高阶函数 ===
    "higher_order": {
        "duan": SnippetEntry(
            "duan",
            "# 段言暂不支持高阶函数语法糖",
            "暂不支持",
        ),
        "yan": SnippetEntry(
            "yan",
            "定义 结果 = 皆 列表 函数 甲 那么 甲 乘 2",
            "「皆」映射",
        ),
        "moyan": SnippetEntry(
            "moyan",
            "列表，每个 相乘 2，打印。",
            "管道操作 + 前缀运算",
        ),
        "mingdao": SnippetEntry(
            "mingdao",
            "# 明道暂不支持高阶函数语法糖",
            "暂不支持",
        ),
        "zhixing": SnippetEntry(
            "zhixing",
            "定 结果 = 皆 列表 函 甲 { 甲 * 2 }",
            "「皆」映射 + 匿名函",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "定 结果 = 皆 列表 函数 甲 { 甲 * 2 }",
            "「皆」映射",
        ),
        "traeyan": SnippetEntry(
            "traeyan",
            "# 趣言暂不支持高阶函数语法糖",
            "暂不支持",
        ),
        "hanyu": SnippetEntry(
            "hanyu",
            "# 翰语暂不支持高阶函数语法糖",
            "暂不支持",
        ),
        "yanlv": SnippetEntry(
            "yanlv",
            "# 言律暂不支持高阶函数语法糖",
            "暂不支持",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "定义 结果 = 皆 列表 函数 甲 那么 甲 乘 2",
            "「皆」映射",
        ),
        "hua": SnippetEntry(
            "hua",
            "# 华语暂不支持高阶函数语法糖",
            "暂不支持",
        ),
    },
}


class SyntaxMatrix:
    """语法对比矩阵引擎"""

    def __init__(self):
        self._concepts = CONCEPTS
        self._snippets = SNIPPETS

    @property
    def concepts(self) -> list[SyntaxConcept]:
        return list(self._concepts)

    @property
    def lang_ids(self) -> list[str]:
        """所有参与对比的语言 ID"""
        ids: set[str] = set()
        for concept_snippets in self._snippets.values():
            ids.update(concept_snippets.keys())
        return sorted(ids)

    def get_concept(self, concept_id: str) -> Optional[SyntaxConcept]:
        """获取概念定义"""
        for c in self._concepts:
            if c.id == concept_id:
                return c
        return None

    def get_snippet(self, concept_id: str, lang_id: str) -> Optional[SnippetEntry]:
        """获取指定概念在指定语言下的代码片段"""
        concept_snippets = self._snippets.get(concept_id, {})
        return concept_snippets.get(lang_id)

    def get_concept_snippets(self, concept_id: str) -> dict[str, SnippetEntry]:
        """获取指定概念在所有语言下的代码片段"""
        return dict(self._snippets.get(concept_id, {}))

    def get_language_snippets(self, lang_id: str) -> dict[str, SnippetEntry]:
        """获取指定语言在所有概念下的代码片段"""
        result: dict[str, SnippetEntry] = {}
        for concept in self._concepts:
            snippet = self._snippets.get(concept.id, {}).get(lang_id)
            if snippet is not None:
                result[concept.id] = snippet
        return result

    def get_matrix(self) -> list[dict]:
        """生成完整的对比矩阵

        Returns:
            [{"concept": SyntaxConcept, "snippets": {lang_id: SnippetEntry}}, ...]
        """
        result = []
        for concept in self._concepts:
            snippets = self._snippets.get(concept.id, {})
            if snippets:
                result.append({"concept": concept, "snippets": dict(snippets)})
        return result

    def get_categories(self) -> list[str]:
        """获取所有概念分类"""
        return sorted(set(c.category for c in self._concepts))

    def get_concepts_by_category(self, category: str) -> list[SyntaxConcept]:
        """按分类获取概念"""
        return [c for c in self._concepts if c.category == category]

    def compute_syntax_style(self) -> dict[str, dict[str, str]]:
        """分析各语言的语法风格特征

        Returns:
            {lang_id: {"运算风格": ..., "语句结束": ..., "代码块": ..., "注释": ...}}
        """
        registry = get_registry()
        styles: dict[str, dict[str, str]] = {}

        for lang_id in self.lang_ids:
            adapter = registry.get(lang_id)
            if adapter is None:
                continue

            features: dict[str, str] = {}

            # 从代码片段推断风格
            var_snippet = self._snippets.get("var_declare", {}).get(lang_id)
            if var_snippet:
                if "设" in var_snippet.code and "为" in var_snippet.code:
                    features["变量风格"] = "设…为…"
                elif "定" in var_snippet.code and "等于" in var_snippet.code:
                    features["变量风格"] = "定…等于…"
                elif "定义" in var_snippet.code:
                    features["变量风格"] = "定义 + ="
                elif "定" in var_snippet.code:
                    features["变量风格"] = "定 + ="

            func_snippet = self._snippets.get("func_def", {}).get(lang_id)
            if func_snippet:
                if "段落" in func_snippet.code:
                    features["函数风格"] = "段落…结束"
                elif "函数" in func_snippet.code and "{" in func_snippet.code:
                    features["函数风格"] = "函数(参数) { }"
                elif "函" in func_snippet.code and "{" in func_snippet.code:
                    features["函数风格"] = "函(参数) { }"
                elif "就是函" in func_snippet.code:
                    features["函数风格"] = "就是函 (前缀)"
                elif "函数" in func_snippet.code and "那么" in func_snippet.code:
                    features["函数风格"] = "函数 + 那么"
                elif "函" in func_snippet.code and "：" in func_snippet.code:
                    features["函数风格"] = "函 + 冒号"

            # 语句结束符
            hello_snippet = self._snippets.get("hello", {}).get(lang_id)
            if hello_snippet:
                if "。" in hello_snippet.code:
                    features["语句结束"] = "中文句号 。"
                else:
                    features["语句结束"] = "换行"

            # 代码块风格
            if_snippet = self._snippets.get("if_else", {}).get(lang_id)
            if if_snippet:
                if "{" in if_snippet.code:
                    features["代码块"] = "花括号 { }"
                elif "：" in if_snippet.code:
                    features["代码块"] = "冒号缩进"
                elif "那么" in if_snippet.code:
                    features["代码块"] = "那么 + 缩进"

            # 运算风格
            assign_snippet = self._snippets.get("var_assign", {}).get(lang_id)
            if assign_snippet:
                if "加等于" in assign_snippet.code:
                    features["运算风格"] = "中文复合赋值"
                elif "加" in assign_snippet.code and "+" not in assign_snippet.code:
                    features["运算风格"] = "中文运算符"
                elif "+" in assign_snippet.code:
                    features["运算风格"] = "ASCII 运算符"

            features["注释"] = adapter.comment_syntax

            styles[lang_id] = features

        return styles

    def generate_html(self, output_path: str | Path | None = None) -> str:
        """生成 HTML 可视化对比页面

        Args:
            output_path: 输出文件路径，None 则只返回 HTML 字符串

        Returns:
            HTML 内容字符串
        """
        registry = get_registry()
        lang_ids = self.lang_ids
        matrix = self.get_matrix()
        styles = self.compute_syntax_style()

        # 语言颜色映射
        color_map: dict[str, str] = {}
        for lang_id in lang_ids:
            adapter = registry.get(lang_id)
            if adapter:
                color_map[lang_id] = adapter.primary_color

        # 构建 HTML
        html = _build_html(lang_ids, matrix, styles, color_map, registry)

        if output_path is not None:
            Path(output_path).write_text(html, encoding="utf-8")

        return html


# ---- HTML 生成 ----


def _build_html(
    lang_ids: list[str],
    matrix: list[dict],
    styles: dict[str, dict[str, str]],
    color_map: dict[str, str],
    registry,
) -> str:
    """构建完整的 HTML 对比页面"""

    # 语言表头
    lang_headers = ""
    for lid in lang_ids:
        adapter = registry.get(lid)
        name = adapter.name if adapter else lid
        version = adapter.version if adapter else ""
        color = color_map.get(lid, "#2C3E50")
        lang_headers += f"""      <th class="lang-header" style="border-top: 3px solid {color}">
        <span class="lang-name">{name}</span><br>
        <span class="lang-id">{lid}</span><br>
        <span class="lang-ver">v{version}</span>
      </th>\n"""

    # 语法风格总览行
    style_rows = ""
    style_labels = {
        "变量风格": "变量声明",
        "函数风格": "函数定义",
        "语句结束": "语句结束",
        "代码块": "代码块",
        "运算风格": "运算符",
        "注释": "注释",
    }
    for style_key, style_label in style_labels.items():
        cells = ""
        for lid in lang_ids:
            feat = styles.get(lid, {})
            val = feat.get(style_key, "—")
            cells += f"      <td>{val}</td>\n"
        style_rows += f"""    <tr>
      <td class="concept-cell">{style_label}</td>
{cells}    </tr>\n"""

    # 概念对比行
    concept_rows = ""
    current_category = ""
    for entry in matrix:
        concept: SyntaxConcept = entry["concept"]
        snippets: dict[str, SnippetEntry] = entry["snippets"]

        # 分类标题行
        if concept.category != current_category:
            current_category = concept.category
            concept_rows += f"""    <tr class="category-row">
      <td colspan="{len(lang_ids) + 1}" class="category-cell">{current_category}</td>
    </tr>\n"""

        cells = ""
        for lid in lang_ids:
            snippet = snippets.get(lid)
            if snippet is None:
                cells += '      <td class="snippet-na">—</td>\n'
            else:
                # HTML 转义
                code_escaped = (
                    snippet.code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                note_html = ""
                if snippet.note:
                    note_html = f'<div class="snippet-note">{snippet.note}</div>'
                cells += f"""      <td class="snippet-cell"><pre class="snippet-code">{code_escaped}</pre>{note_html}</td>\n"""

        difficulty_badge = ""
        if concept.difficulty:
            diff_class = {
                "入门": "diff-beginner",
                "简单": "diff-easy",
                "中等": "diff-medium",
                "困难": "diff-hard",
            }.get(concept.difficulty, "")
            difficulty_badge = (
                f' <span class="difficulty-badge {diff_class}">{concept.difficulty}</span>'
            )

        concept_rows += f"""    <tr>
      <td class="concept-cell">{concept.title}{difficulty_badge}<div class="concept-desc">{concept.description}</div></td>
{cells}    </tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>言埠 YanPub — 中文编程语言语法对比矩阵</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --hover: #1f2937;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, "Segoe UI", "Noto Sans SC", sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 24px;
      line-height: 1.6;
    }}
    .container {{
      max-width: 100%;
      overflow-x: auto;
    }}
    h1 {{
      text-align: center;
      font-size: 28px;
      margin-bottom: 8px;
    }}
    .subtitle {{
      text-align: center;
      color: var(--text-muted);
      margin-bottom: 24px;
      font-size: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 1200px;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 10px 12px;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: var(--card-bg);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .lang-header {{
      text-align: center;
      min-width: 140px;
    }}
    .lang-name {{
      font-size: 15px;
      font-weight: 600;
      display: block;
    }}
    .lang-id {{
      font-size: 11px;
      color: var(--text-muted);
      font-family: monospace;
    }}
    .lang-ver {{
      font-size: 10px;
      color: var(--text-muted);
    }}
    .concept-header {{
      text-align: center;
      min-width: 160px;
    }}
    .concept-cell {{
      background: var(--card-bg);
      font-weight: 600;
      position: sticky;
      left: 0;
      z-index: 5;
      min-width: 160px;
    }}
    .concept-desc {{
      font-weight: 400;
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 2px;
    }}
    .category-row td {{
      background: #1c2333;
      font-size: 14px;
      font-weight: 700;
      text-align: center;
      color: var(--accent);
      padding: 6px;
      letter-spacing: 2px;
    }}
    .snippet-cell {{
      background: var(--bg);
    }}
    .snippet-code {{
      font-family: "Fira Code", "Cascadia Code", "Source Code Pro", monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-all;
      margin: 0;
      color: #c9d1d9;
    }}
    .snippet-note {{
      font-size: 10px;
      color: var(--accent);
      margin-top: 4px;
      font-style: italic;
    }}
    .snippet-na {{
      text-align: center;
      color: var(--text-muted);
      background: var(--bg);
    }}
    .difficulty-badge {{
      display: inline-block;
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 8px;
      font-weight: 400;
      margin-left: 4px;
      vertical-align: middle;
    }}
    .diff-beginner {{ background: #1a4731; color: #3fb950; }}
    .diff-easy {{ background: #1a3a5c; color: #58a6ff; }}
    .diff-medium {{ background: #4a3000; color: #d29922; }}
    .diff-hard {{ background: #4a1020; color: #f85149; }}
    .style-section {{
      margin-bottom: 32px;
    }}
    .style-section h2 {{
      font-size: 18px;
      margin-bottom: 12px;
      color: var(--accent);
    }}
    .legend {{
      text-align: center;
      margin-bottom: 16px;
      font-size: 12px;
      color: var(--text-muted);
    }}
    tr:hover td {{
      background: var(--hover);
    }}
    tr:hover .concept-cell {{
      background: #1c2531;
    }}
  </style>
</head>
<body>
  <h1>🧮 中文编程语言语法对比矩阵</h1>
  <p class="subtitle">
    言埠 YanPub — 同一概念，十种写法 · 共 {len(lang_ids)} 种语言 · {len(matrix)} 个语法概念
  </p>
  <p class="legend">
    难度：
    <span class="difficulty-badge diff-beginner">入门</span>
    <span class="difficulty-badge diff-easy">简单</span>
    <span class="difficulty-badge diff-medium">中等</span>
    <span class="difficulty-badge diff-hard">困难</span>
  </p>
  <div class="container">
    <table>
      <thead>
        <tr>
          <th class="concept-header">语法概念</th>
{lang_headers}        </tr>
      </thead>
      <tbody>
    <tr class="category-row">
      <td colspan="{len(lang_ids) + 1}" class="category-cell">语法风格总览</td>
    </tr>
{style_rows}{concept_rows}      </tbody>
    </table>
  </div>
</body>
</html>"""

    return html
