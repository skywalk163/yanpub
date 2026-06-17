"""基于规则的翻译引擎 — 不依赖外部 API

提供关键字、分类的中文→英/日/韩翻译映射，
以及文档结构的批量翻译能力。
"""

from __future__ import annotations


class RuleBasedTranslator:
    """基于规则的翻译引擎（不依赖外部 API）

    通过关键字映射表、分类映射表和消息键推断实现翻译。
    """

    # 关键字翻译映射
    _KEYWORD_TRANSLATIONS: dict[str, dict[str, str]] = {
        "段落": {"en": "Function", "ja": "関数", "ko": "함수"},
        "设": {"en": "Set/Let", "ja": "設定", "ko": "설정"},
        "定义": {"en": "Define", "ja": "定義", "ko": "정의"},
        "如果": {"en": "If", "ja": "もし", "ko": "만약"},
        "若": {"en": "If", "ja": "もし", "ko": "만약"},
        "当": {"en": "While", "ja": "繰り返し", "ko": "반복"},
        "返回": {"en": "Return", "ja": "戻る", "ko": "반환"},
        "类": {"en": "Class", "ja": "クラス", "ko": "클래스"},
        "打印": {"en": "Print", "ja": "出力", "ko": "출력"},
        "否则": {"en": "Else", "ja": "そうでなければ", "ko": "아니면"},
        "遍历": {"en": "For Each", "ja": "繰り返し", "ko": "반복"},
        "尝试": {"en": "Try", "ja": "試す", "ko": "시도"},
        "捕获": {"en": "Catch", "ja": "キャッチ", "ko": "캐치"},
        "抛出": {"en": "Throw", "ja": "スロー", "ko": "던지기"},
        "最终": {"en": "Finally", "ja": "最後に", "ko": "최종"},
        "导入": {"en": "Import", "ja": "インポート", "ko": "임포트"},
        "导出": {"en": "Export", "ja": "エクスポート", "ko": "익스포트"},
        "继承": {"en": "Inherit/Extends", "ja": "継承", "ko": "상속"},
        "属性": {"en": "Property", "ja": "プロパティ", "ko": "속성"},
        "构造": {"en": "Constructor", "ja": "コンストラクタ", "ko": "생성자"},
        "新建": {"en": "New", "ja": "新規", "ko": "새로 만들기"},
        "真": {"en": "True", "ja": "真", "ko": "참"},
        "假": {"en": "False", "ja": "偽", "ko": "거짓"},
        "空": {"en": "None/Null", "ja": "ヌル", "ko": "널"},
        "函数": {"en": "Function", "ja": "関数", "ko": "함수"},
        "重复": {"en": "Repeat", "ja": "反復", "ko": "반복"},
        "跳出": {"en": "Break", "ja": "ブレーク", "ko": "브레이크"},
        "继续": {"en": "Continue", "ja": "継続", "ko": "계속"},
        "结束": {"en": "End", "ja": "終了", "ko": "끝"},
        "定": {"en": "Define", "ja": "定義", "ko": "정의"},
        "函": {"en": "Function", "ja": "関数", "ko": "함수"},
        "赋值": {"en": "Assign", "ja": "代入", "ko": "할당"},
        "变量": {"en": "Variable", "ja": "変数", "ko": "변수"},
        "常量": {"en": "Constant", "ja": "定数", "ko": "상수"},
        "列表": {"en": "List", "ja": "リスト", "ko": "리스트"},
        "字典": {"en": "Dictionary", "ja": "辞書", "ko": "딕셔너리"},
        "集": {"en": "Set", "ja": "セット", "ko": "집합"},
        "元组": {"en": "Tuple", "ja": "タプル", "ko": "튜플"},
        "匹配": {"en": "Match", "ja": "マッチ", "ko": "매치"},
        "读取": {"en": "Read", "ja": "読み取り", "ko": "읽기"},
        "输出": {"en": "Output", "ja": "出力", "ko": "출력"},
        "映射": {"en": "Map", "ja": "マップ", "ko": "맵"},
        "过滤": {"en": "Filter", "ja": "フィルタ", "ko": "필터"},
        "归约": {"en": "Reduce", "ja": "リデュース", "ko": "리듀스"},
        "印": {"en": "Print", "ja": "出力", "ko": "출력"},
        "显示": {"en": "Display", "ja": "表示", "ko": "표시"},
    }

    # 分类翻译映射
    _CATEGORY_TRANSLATIONS: dict[str, dict[str, str]] = {
        "定义": {"en": "Definition", "ja": "定義", "ko": "정의"},
        "控制流": {"en": "Control Flow", "ja": "制御フロー", "ko": "제어 흐름"},
        "函数": {"en": "Function", "ja": "関数", "ko": "함수"},
        "运算": {"en": "Operator", "ja": "演算", "ko": "연산"},
        "模块": {"en": "Module", "ja": "モジュール", "ko": "모듈"},
        "IO": {"en": "I/O", "ja": "入出力", "ko": "입출력"},
        "异常": {"en": "Exception", "ja": "例外", "ko": "예외"},
        "数据结构": {"en": "Data Structure", "ja": "データ構造", "ko": "데이터 구조"},
        "条件": {"en": "Condition", "ja": "条件", "ko": "조건"},
        "复合赋值": {"en": "Compound Assignment", "ja": "複合代入", "ko": "복합 대입"},
        "逻辑值": {"en": "Boolean Literal", "ja": "論理値", "ko": "논리값"},
        "类型": {"en": "Type", "ja": "型", "ko": "타입"},
        "类与对象": {"en": "Class & Object", "ja": "クラスとオブジェクト", "ko": "클래스와 객체"},
        "函数式": {"en": "Functional", "ja": "関数型", "ko": "함수형"},
        "匹配": {"en": "Pattern Matching", "ja": "パターンマッチ", "ko": "패턴 매칭"},
        "DSL": {"en": "DSL", "ja": "DSL", "ko": "DSL"},
        "其他": {"en": "Other", "ja": "その他", "ko": "기타"},
    }

    # 文档字段翻译映射
    _FIELD_TRANSLATIONS: dict[str, dict[str, str]] = {
        "变量/常量声明与赋值": {"en": "Variable/Constant declaration and assignment", "ja": "変数/定数の宣言と代入", "ko": "변수/상수 선언 및 할당"},
        "函数定义与声明": {"en": "Function definition and declaration", "ja": "関数の定義と宣言", "ko": "함수 정의 및 선언"},
        "条件判断与循环控制": {"en": "Conditionals and loop control", "ja": "条件分岐とループ制御", "ko": "조건문과 루프 제어"},
        "条件表达式": {"en": "Conditional expression", "ja": "条件式", "ko": "조건식"},
        "异常处理机制": {"en": "Exception handling", "ja": "例外処理メカニズム", "ko": "예외 처리 메커니즘"},
        "模块导入与导出": {"en": "Module import and export", "ja": "モジュールのインポートとエクスポート", "ko": "모듈 임포트와 익스포트"},
        "算术/比较/逻辑运算": {"en": "Arithmetic/Comparison/Logical operators", "ja": "算術/比較/論理演算", "ko": "산술/비교/논리 연산"},
        "复合赋值运算符（如 加等于）": {"en": "Compound assignment operators (e.g. +=)", "ja": "複合代入演算子（例: +=）", "ko": "복합 대입 연산자 (예: +=)"},
        "数据结构操作（列表/字典/集合）": {"en": "Data structure operations (List/Dict/Set)", "ja": "データ構造操作（リスト/辞書/セット）", "ko": "데이터 구조 조작 (리스트/딕셔너리/집합)"},
        "布尔/空值字面量": {"en": "Boolean/Null literals", "ja": "論理/ヌルリテラル", "ko": "불/널 리터럴"},
        "类型标注与内建类型": {"en": "Type annotations and built-in types", "ja": "型アノテーションと組み込み型", "ko": "타입 어노테이션과 내장 타입"},
        "输入输出操作": {"en": "I/O operations", "ja": "入出力操作", "ko": "입출력 조작"},
        "面向对象编程": {"en": "Object-Oriented Programming", "ja": "オブジェクト指向プログラミング", "ko": "객체지향 프로그래밍"},
        "函数式编程（映射/过滤/归约）": {"en": "Functional programming (Map/Filter/Reduce)", "ja": "関数型プログラミング（マップ/フィルタ/リデュース）", "ko": "함수형 프로그래밍 (맵/필터/리듀스)"},
        "模式匹配": {"en": "Pattern matching", "ja": "パターンマッチ", "ko": "패턴 매칭"},
        "领域特定语言与宏": {"en": "DSL and macros", "ja": "DSLとマクロ", "ko": "DSL과 매크로"},
    }

    def translate(self, text: str, source_lang: str = "zh", target_lang: str = "en") -> str:
        """翻译文本

        规则（按优先级）：
        1. 查关键字映射表
        2. 查分类映射表
        3. 查文档字段映射表
        4. 回退到原文

        Args:
            text: 待翻译文本
            source_lang: 源语言（默认 "zh"）
            target_lang: 目标语言

        Returns:
            翻译后的文本
        """
        if source_lang == target_lang:
            return text

        # 1. 查关键字映射表
        kw_trans = self._KEYWORD_TRANSLATIONS.get(text, {})
        if target_lang in kw_trans:
            return kw_trans[target_lang]

        # 2. 查分类映射表
        cat_trans = self._CATEGORY_TRANSLATIONS.get(text, {})
        if target_lang in cat_trans:
            return cat_trans[target_lang]

        # 3. 查文档字段映射表
        field_trans = self._FIELD_TRANSLATIONS.get(text, {})
        if target_lang in field_trans:
            return field_trans[target_lang]

        # 4. 回退到原文
        return text

    def translate_dict(self, data: dict, target_lang: str, fields: list[str] | None = None) -> dict:
        """翻译 dict 中指定字段的值

        Args:
            data: 原始字典
            target_lang: 目标语言
            fields: 需要翻译的字段名列表（默认翻译所有可翻译字段）

        Returns:
            翻译后的字典（浅拷贝，原字典不变）
        """
        # 默认可翻译字段
        default_fields = [
            "category", "description", "concept",
            "site_name", "site_description",
            "name", "comment_syntax",
        ]
        target_fields = fields or default_fields

        result = dict(data)
        for field in target_fields:
            if field in result and isinstance(result[field], str):
                result[field] = self.translate(result[field], target_lang=target_lang)

        return result

    def translate_keyword_doc(self, keyword_doc_dict: dict, target_lang: str) -> dict:
        """翻译关键字文档条目（dict 形式）

        Args:
            keyword_doc_dict: KeywordDoc 的字典表示
            target_lang: 目标语言

        Returns:
            翻译后的关键字文档字典
        """
        result = dict(keyword_doc_dict)
        if "keyword" in result:
            result["keyword_display"] = self.translate(result["keyword"], target_lang=target_lang)
        if "category" in result:
            result["category"] = self.translate(result["category"], target_lang=target_lang)
        if "description" in result:
            result["description"] = self.translate(result["description"], target_lang=target_lang)
        return result
