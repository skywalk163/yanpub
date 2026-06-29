"""语法对比矩阵 — 数据层

包含预定义的语法概念列表和各语言的代码片段。
本文件从 syntax_matrix.py 拆分而来，仅包含纯数据定义。
"""

from __future__ import annotations

from yanpub.core.syntax_matrix import SnippetEntry


# ---- 预定义的语法概念（15个核心概念） ----

CONCEPTS_ARGS: list[tuple] = [
    ("hello", "你好世界", "基础", "最简单的程序", "入门"),
    ("var_declare", "变量声明", "基础", "声明并赋值一个变量", "入门"),
    ("var_assign", "变量赋值/修改", "基础", "修改变量的值", "入门"),
    ("func_def", "函数定义", "函数", "定义一个带参数和返回值的函数", "入门"),
    ("func_call", "函数调用", "函数", "调用函数并使用返回值", "入门"),
    ("if_else", "条件语句", "控制流", "if-else 条件判断", "入门"),
    ("while_loop", "while 循环", "控制流", "当型循环", "简单"),
    ("for_loop", "遍历循环", "控制流", "遍历列表/范围", "简单"),
    ("list_ops", "列表操作", "数据结构", "创建列表、访问元素", "简单"),
    ("dict_ops", "字典操作", "数据结构", "创建字典、存取键值", "中等"),
    ("class_def", "类定义", "面向对象", "定义类、属性、方法", "中等"),
    ("try_catch", "异常处理", "异常", "try-catch 捕获异常", "中等"),
    ("import_mod", "模块导入", "模块", "导入外部模块", "简单"),
    ("recursion", "递归函数", "函数", "递归调用自身", "中等"),
    ("higher_order", "高阶函数", "函数", "map/filter/reduce 风格", "困难"),
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
        "zhixing": SnippetEntry("zhixing", '"你好，世界！"，印。', "管道式风格"),
        "xinyu": SnippetEntry("xinyu", '印 "你好，世界！"。', "印 + 中文句号"),
        "traeyan": SnippetEntry("traeyan", '印"你好，世界！"。', "无括号，动词吞噬"),
        "hanyu": SnippetEntry("hanyu", '打印("你好，世界！")', "C 风格语法"),
        "yanlv": SnippetEntry("yanlv", '输出 "你好，世界！"', "意合式风格"),
        "yanzhi": SnippetEntry("yanzhi", '打印("你好，世界！")', "C 风格语法"),
        "hua": SnippetEntry("hua", '输出 "你好，世界！"', "无括号输出"),
    },
    # === 变量声明 ===
    "var_declare": {
        "duan": SnippetEntry("duan", "设甲为四十二。", "「设…为…」统一格式"),
        "yan": SnippetEntry("yan", "定义 甲 = 42", "定义 + 等号赋值"),
        "moyan": SnippetEntry("moyan", "定义 甲 = 42。", "定义 + 等号赋值 + 中文句号"),
        "mingdao": SnippetEntry("mingdao", "定义 甲 = 42", "定义 + 等号赋值"),
        "zhixing": SnippetEntry("zhixing", "定甲是42。", "「定…是…」声明 + 句号"),
        "xinyu": SnippetEntry("xinyu", "定 x = 10。", "「定…=…」+ 中文句号"),
        "traeyan": SnippetEntry("traeyan", "定甲等于42。", "无空格，句号结束"),
        "hanyu": SnippetEntry("hanyu", "定义 甲 = 42", "定义 + 等号赋值"),
        "yanlv": SnippetEntry("yanlv", "定 甲 是 42", "「定…是…」声明"),
        "yanzhi": SnippetEntry("yanzhi", "定义 甲 = 42", "定义 + 等号赋值"),
        "hua": SnippetEntry("hua", "变量 甲 为 42", "「变量…为…」声明"),
    },
    "var_assign": {
        "duan": SnippetEntry("duan", "设甲为甲加一。", "重新设值（中文运算符）"),
        "yan": SnippetEntry("yan", "赋值 甲 = 甲 + 1", "显式「赋值」关键字"),
        "moyan": SnippetEntry("moyan", "赋值 甲 = 相加 甲 1。", "赋值 + 前缀运算 + 中文句号"),
        "mingdao": SnippetEntry("mingdao", "赋值 甲 = 甲 + 1", "显式「赋值」关键字"),
        "zhixing": SnippetEntry("zhixing", "设甲是甲加1。", "「设…是…」赋值 + 中文运算"),
        "xinyu": SnippetEntry("xinyu", "x = x加1。", "直接赋值 + 中文运算 + 句号"),
        "traeyan": SnippetEntry("traeyan", "甲加等于1。", "复合赋值运算符"),
        "hanyu": SnippetEntry("hanyu", "为 甲 = 甲 加 1", "「为」赋值 + 中文运算"),
        "yanlv": SnippetEntry("yanlv", "甲 是 甲 加 1", "「是」赋值 + 中文运算"),
        "yanzhi": SnippetEntry("yanzhi", "赋值 甲 = 甲 + 1", "显式「赋值」关键字"),
        "hua": SnippetEntry("hua", "甲 为 甲 加 1", "「为」重新赋值 + 中文运算"),
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
            "zhixing", "定dbl是函x 乘 x 2。", "单行函数 + 中文运算 + 句号"
        ),
        "xinyu": SnippetEntry("xinyu", "定 求和 = 函 a， b：\n  返回 a加b。\n。", "「定…=函…：…。」结构"),
        "traeyan": SnippetEntry(
            "traeyan", "定求和等于函 甲 乙：\n  返回 甲加乙。\n结束", "无括号函数定义"
        ),
        "hanyu": SnippetEntry("hanyu", "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "C 风格花括号"),
        "yanlv": SnippetEntry("yanlv", "定求和是函甲、乙：\n  回甲加乙。", "「定…是函…：」+ 回 + 缩进块"),
        "yanzhi": SnippetEntry("yanzhi", "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}", "C 风格花括号"),
        "hua": SnippetEntry("hua", "函数 求和\n  参数 甲 为 整数\n  参数 乙 为 整数\n  返回 甲 加 乙", "函数…参数…为类型…返回 + 缩进块"),
    },
    "func_call": {
        "duan": SnippetEntry("duan", "设结果为 求和(三, 五)。", "括号调用 + 中文运算"),
        "yan": SnippetEntry("yan", "定义 结果 = 求和 3 5", "空格分隔参数（前缀风格）"),
        "moyan": SnippetEntry("moyan", "定义 结果 = 求和 3 5。", "空格分隔参数（前缀风格）+ 中文句号"),
        "mingdao": SnippetEntry("mingdao", "定义 结果 = 求和(3, 5)", "括号调用"),
        "zhixing": SnippetEntry("zhixing", "dbl 5，印。", "空格调用 + 管道印"),
        "xinyu": SnippetEntry("xinyu", "印 求和(3， 5)。", "括号调用 + 中文逗号 + 句号"),
        "traeyan": SnippetEntry("traeyan", "定结果等于求和(3, 5)。", "括号调用 + 句号"),
        "hanyu": SnippetEntry("hanyu", "定义 结果 = 求和(3, 5)", "括号调用"),
        "yanlv": SnippetEntry("yanlv", "求和 3 5，印。", "空格调用 + 管道印"),
        "yanzhi": SnippetEntry("yanzhi", "定义 结果 = 求和(3, 5)", "括号调用"),
        "hua": SnippetEntry("hua", "变量 结果 为 求和(3, 5)", "括号调用 + 逗号分隔参数"),
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
            '若甲大乙则"甲大"否则"乙大"，印。',
            "若…则…否则 + 管道印",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            '若 x大于y：\n  印 "甲大"。\n否则：\n  印 "乙大"。\n。',
            "若…否则 + 缩进块 + 句号",
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
            '若甲大乙就印"甲大"。\n不然就印"乙大"。',
            "若…就…不然就… + 印",
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
            "定n是5。\n当n大0：\n  印n。\n  设n是n减1。\n。",
            "当 + 缩进块 + 句号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "当 n大于0：\n  印 n。\n  n = n减1。\n。",
            "当 + 缩进块 + 句号",
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
            "当 甲 小于 10：\n  印甲。\n  甲 是 甲 加 1。\n。",
            "当 + 缩进块 + 句号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "循环当 甲 < 10 {\n  打印(甲)\n  甲 = 甲 + 1\n}",
            "循环当 + 花括号",
        ),
        "hua": SnippetEntry(
            "hua",
            "当 甲 小于 10\n  输出(字符串(甲))\n  甲 为 甲 加 1",
            "当… + 缩进块 + 中文运算",
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
            "遍历i从1到5：\n  印i。\n。",
            "遍历…从…到 + 缩进块 + 句号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "遍历 i 于 范围(1， 6)：\n  印 i。\n。",
            "遍历…于…范围() + 缩进块 + 句号",
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
            "遍历i从1到5：\n  印i。\n。",
            "遍历…从…到 + 缩进块 + 句号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "遍历 甲 于中 列表 {\n  打印(甲)\n}",
            "遍历…于中 + 花括号",
        ),
        "hua": SnippetEntry(
            "hua",
            "对于 值 在 [1, 2, 3]\n  输出(字符串(值))",
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
            "定甲是列3 5 8。\n甲算0，印。\n长甲，印。",
            "「列…」+ 算索引 + 长度 + 句号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "定 列表 = 【3， 5， 8】。\n定 乙 = 列表[0]。",
            "【】列表 + 方括号索引 + 句号",
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
            "定 甲 是 列3 5 8。\n甲算0，印。\n长甲，印。",
            "「列…」+ 算索引 + 长度 + 句号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "定义 甲 = [3, 5, 8]\n定义 乙 = 甲[0]\n定义 丙 = 长度(甲)",
            "C 风格",
        ),
        "hua": SnippetEntry(
            "hua",
            "变量 甲 为 [3, 5, 8]\n变量 乙 为 甲[0]\n变量 丙 为 大小(甲)",
            "变量…为 + 方括号索引 + 函数调用",
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
            '定甲是字典 "名" "张三" "年龄" 18。\n键甲 "名"，印。',
            "字典构造 + 键取值 + 句号",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            '定 甲 = 字典()。\n甲["名"] = "张三"。',
            "字典() + 方括号赋值 + 句号",
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
            '定张三是典姓名是"张三"、年龄是25。\n张三·姓名，印。',
            "「典…是…」对象 + ·取值",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            '定义 甲 = {"名": "张三"}\n定义 乙 = 甲["名"]',
            "花括号字面量",
        ),
        "hua": SnippetEntry(
            "hua",
            '变量 甲 为 创建字典()\n甲["名"] 为 "张三"\n变量 乙 为 甲["名"]',
            "创建字典() + 方括号赋值/取值",
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
            "# 知行暂不支持异常处理",
            "暂不支持",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "尝试：\n  定 甲 = 危险操作()。\n捕获 错误：\n  印 错误。\n。",
            "尝试…捕获 + 缩进块 + 句号",
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
            "尝试：\n  定甲是危险操作()。\n捕获错误：\n  印错误。\n。",
            "尝试…捕获 + 缩进块 + 句号",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "尝试 {\n  定义 甲 = 危险操作()\n} 捕获 错误 {\n  打印(错误)\n}",
            "尝试…捕获 + 花括号",
        ),
        "hua": SnippetEntry(
            "hua",
            "尝试\n  变量 甲 为 危险操作()\n捕获 错误 为 文本\n  输出(错误)\n最终\n  输出 \"完成\"",
            "尝试…捕获…最终 + 缩进块",
        ),
    },
    "import_mod": {
        "duan": SnippetEntry("duan", "导入《数学》。", "书名号模块名"),
        "yan": SnippetEntry("yan", "导入 数学", "空格分隔"),
        "moyan": SnippetEntry("moyan", "导入 数学", "空格分隔"),
        "mingdao": SnippetEntry("mingdao", "导入 数学", "空格分隔"),
        "zhixing": SnippetEntry("zhixing", "导入 数学", "空格分隔"),
        "xinyu": SnippetEntry("xinyu", "导入 从 数学 中的 [平方根]", "从…中的 选择性导入"),
        "traeyan": SnippetEntry("traeyan", "导入 数学", "空格分隔"),
        "hanyu": SnippetEntry("hanyu", "导入 数学", "空格分隔"),
        "yanlv": SnippetEntry("yanlv", "导入 数学", "空格分隔"),
        "yanzhi": SnippetEntry("yanzhi", "导入 数学", "空格分隔"),
        "hua": SnippetEntry("hua", "导入 从 数学库 中的 [平方根]", "从…中的 选择性导入"),
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
            "定dbl是函x 乘 x 2。\ndbl 5，印。",
            "单行函数 + 管道印",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "定 斐波那契 = 函 n：\n  若 n小于2：\n    返回 n。\n  否则：\n    返回 斐波那契(n减1)加斐波那契(n减2)。\n  。\n。",
            "函…若…否则…递归 + 中文运算 + 句号",
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
            "定斐波那契是函甲：\n  若甲小2则回甲。\n  回斐波那契(甲减1)加斐波那契(甲减2)。\n。",
            "定…是函…若…则…回 + 缩进块",
        ),
        "yanzhi": SnippetEntry(
            "yanzhi",
            "函数 斐波那契(甲) {\n  如果 甲 小于 2 那么 返回 甲\n  返回 斐波那契(甲-1) + 斐波那契(甲-2)\n}",
            "中文运算递归",
        ),
        "hua": SnippetEntry(
            "hua",
            "函数 斐波那契\n  参数 甲 为 整数\n  如果 甲 小于等于 1\n    返回 1\n  返回 甲 乘 斐波那契(甲 减 1)",
            "函数递归 + 缩进块 + 中文运算",
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
            "范围10，皆乘2，印。",
            "管道式 + 皆映射 + 印",
        ),
        "xinyu": SnippetEntry(
            "xinyu",
            "遍历 i 于 范围(10)：\n  印 i乘2。\n。",
            "遍历…于…范围() + 中文运算 + 句号",
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
            "范围10，皆乘2，印。",
            "管道式 + 皆映射 + 印",
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
