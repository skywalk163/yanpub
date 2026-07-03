"""翰语运行器 — 编译并执行翰语代码

优先使用 LLVM JIT/子进程执行，若不可用则回退到 Python AST 解释器。
用法: python -m yanpub.adapters.hanyu.runner <file.翰>
      echo '打印"你好"' | python -m yanpub.adapters.hanyu.runner -
"""
from __future__ import annotations

import sys
import os


def _try_native_execute(ir: str) -> tuple[str, str, int] | None:
    """尝试使用翰语原生 execute_ir（JIT/lli/clang）"""
    try:
        # 确保 hanyu 包可用
        hanyu_src = os.environ.get("HANYU_DIR", "")
        if hanyu_src and os.path.isdir(os.path.join(hanyu_src, "src")):
            sys.path.insert(0, os.path.join(hanyu_src, "src"))

        from hanyu.compiler import execute_ir
        stdout, stderr, rc = execute_ir(ir, mode='jit')
        if rc == 0 and not stderr:
            return (stdout, stderr, rc)
        # JIT 失败，尝试 subprocess
        stdout, stderr, rc = execute_ir(ir, mode='subprocess')
        if rc == 0:
            return (stdout, stderr, rc)
        return None
    except Exception:
        return None


class _HanyuInterpreter:
    """简易 AST 解释器 — 翰语核心子集的 Python 回退执行

    支持的语法：定义、赋值、函数定义/调用、打印、算术/比较/逻辑运算、
    如果/那么/否则、循环当满、对于、列表、字符串、返回。
    不支持：结构体、导入、WASM、GC、JIT。
    """

    # 延迟导入的 AST 模块（首次使用时加载）
    _H: object = None

    @classmethod
    def _get_ast(cls):
        if cls._H is None:
            from hanyu import ast as _ast
            cls._H = _ast
        return cls._H

    def __init__(self):
        self.globals: dict = {}
        self.output: list[str] = []

    def run(self, ast) -> str:
        """执行 AST 并返回输出文本"""
        if ast is None:
            return ""
        try:
            H = self._get_ast()
            if isinstance(ast, H.Program):
                for stmt in ast.statements:
                    self._exec_stmt(stmt)
        except Exception as e:
            self.output.append(f"解释器错误: {e}")
        return "\n".join(self.output)

    def _exec_stmt(self, node) -> object:
        """执行一个语句节点"""
        H = self._get_ast()

        if isinstance(node, H.Definition):
            val = self._eval(node.value)
            name = self._mangle(node.name)
            self.globals[name] = val

        elif isinstance(node, H.Assignment):
            val = self._eval(node.value)
            name = self._mangle(node.name)
            # 检查是否是列表下标赋值
            if hasattr(node, 'index') and node.index is not None:
                idx = self._eval(node.index)
                lst = self.globals.get(name, [])
                if isinstance(lst, list) and 0 <= idx < len(lst):
                    lst[idx] = val
            else:
                self.globals[name] = val

        elif isinstance(node, H.FunctionDef):
            name = self._mangle(node.name)
            self.globals[name] = node  # 存储函数定义

        elif isinstance(node, H.ExpressionStmt):
            self._eval(node.expr)

        elif isinstance(node, H.IfStmt):
            cond = self._eval(node.condition)
            if cond:
                for s in (node.then_block or []):
                    self._exec_stmt(s)
            else:
                for s in (node.else_block or []):
                    self._exec_stmt(s)

        elif isinstance(node, H.WhileStmt):
            iterations = 0
            while self._eval(node.condition) and iterations < 100000:
                for s in (node.body or []):
                    r = self._exec_stmt(s)
                    if isinstance(r, _ReturnSignal):
                        return r
                iterations += 1

        elif isinstance(node, H.ForStmt):
            iterable = self._eval(node.iterable)
            var_name = self._mangle(node.var)
            if isinstance(iterable, (list, range)):
                for item in iterable:
                    self.globals[var_name] = item
                    for s in (node.body or []):
                        r = self._exec_stmt(s)
                        if isinstance(r, _ReturnSignal):
                            return r

        elif isinstance(node, H.ReturnStmt):
            val = self._eval(node.value) if node.value else None
            return _ReturnSignal(val)

        elif isinstance(node, H.BreakStmt):
            return _BreakSignal()

        elif isinstance(node, H.ContinueStmt):
            return _ContinueSignal()

        return None

    def _eval(self, node) -> object:
        """求值一个表达式节点"""
        H = self._get_ast()

        if isinstance(node, H.NumberLiteral):
            # hanyu AST 中 NumberLiteral.value 是字符串（如 '42'），需转换
            v = node.value
            if isinstance(v, str):
                try:
                    return int(v) if '.' not in v else float(v)
                except (ValueError, TypeError):
                    return 0
            return v

        if isinstance(node, H.StringLiteral):
            return node.value

        if isinstance(node, H.BooleanLiteral):
            return node.value

        if isinstance(node, H.Identifier):
            name = self._mangle(node.name)
            return self.globals.get(name, 0)

        if isinstance(node, H.ListLiteral):
            return [self._eval(e) for e in (node.elements or [])]

        if isinstance(node, H.UnaryExpr):
            val = self._eval(node.operand)
            op = node.op
            if op in ('负', '-'):
                return -val
            return val

        if isinstance(node, H.BinaryExpr):
            return self._eval_binary(node)

        if isinstance(node, H.FunctionCall):
            return self._eval_call(node)

        if isinstance(node, H.FieldAccess):
            obj = self._eval(node.object)
            if isinstance(obj, dict):
                return obj.get(node.field, 0)
            return 0

        return 0

    def _eval_binary(self, node) -> object:
        """求值二元表达式"""
        left = self._eval(node.left)
        op = node.op

        # 短路逻辑运算
        if op in ('并且', 'and'):
            return left and self._eval(node.right)
        if op in ('或者', 'or'):
            return left or self._eval(node.right)

        right = self._eval(node.right)

        ops = {
            '加': lambda a, b: a + b, '+': lambda a, b: a + b,
            '减': lambda a, b: a - b, '-': lambda a, b: a - b,
            '乘': lambda a, b: a * b, '*': lambda a, b: a * b,
            '除': lambda a, b: a // b if isinstance(a, int) and isinstance(b, int) else a / b,
            '/': lambda a, b: a // b if isinstance(a, int) and isinstance(b, int) else a / b,
            '余': lambda a, b: a % b, '%': lambda a, b: a % b,
            '等于': lambda a, b: a == b, '==': lambda a, b: a == b,
            '不等': lambda a, b: a != b, '!=': lambda a, b: a != b,
            '不等于': lambda a, b: a != b,
            '大于': lambda a, b: a > b, '>': lambda a, b: a > b,
            '小于': lambda a, b: a < b, '<': lambda a, b: a < b,
            '大于等于': lambda a, b: a >= b, '>=': lambda a, b: a >= b,
            '小于等于': lambda a, b: a <= b, '<=': lambda a, b: a <= b,
            '大于等': lambda a, b: a >= b,
            '小于等': lambda a, b: a <= b,
            '右移': lambda a, b: a >> b, '>>': lambda a, b: a >> b,
            '左移': lambda a, b: a << b, '<<': lambda a, b: a << b,
        }

        if op in ops:
            try:
                return ops[op](left, right)
            except (TypeError, ZeroDivisionError):
                return 0

        # 字符串拼接
        if op in ('加', '+') and isinstance(left, str):
            return str(left) + str(right)

        return 0

    def _eval_call(self, node) -> object:
        """求值函数调用"""
        H = self._get_ast()
        # node.func 是 Identifier 或表达式节点
        if isinstance(node.func, H.Identifier):
            func_name = node.func.name
        elif isinstance(node.func, str):
            func_name = node.func
        else:
            func_name = self._eval(node.func)
        args = [self._eval(a) for a in (node.args or [])]

        # 内置函数
        builtins = {
            '打印': self._builtin_print,
            '打印字符串': self._builtin_print_str,
            '长度': lambda a: len(a) if isinstance(a, (list, str)) else 0,
            '调用': lambda *a: a[0](*a[1:]) if callable(a[0]) else 0,
        }

        mangled = self._mangle(func_name)
        if func_name in builtins:
            return builtins[func_name](*args)
        if mangled in builtins:
            return builtins[mangled](*args)

        # 用户函数
        func_def = self.globals.get(mangled)
        if func_def is None:
            func_def = self.globals.get(func_name)
        if isinstance(func_def, H.FunctionDef):
            return self._call_user_func(func_def, args)

        return 0

    def _call_user_func(self, func_def, args) -> object:
        """调用用户定义的函数"""
        H = self._get_ast()
        # 保存当前作用域
        saved = dict(self.globals)

        # 绑定参数（params 是字符串列表，如 ['赵a', '赵b']）
        for i, param in enumerate(func_def.params):
            pname = self._mangle(param)
            self.globals[pname] = args[i] if i < len(args) else 0

        # 执行函数体
        result = None
        for stmt in (func_def.body or []):
            r = self._exec_stmt(stmt)
            if isinstance(r, _ReturnSignal):
                result = r.value
                break

        # 恢复作用域（但保留全局函数定义）
        new_globals = dict(self.globals)
        self.globals = saved
        for k, v in new_globals.items():
            if isinstance(v, H.FunctionDef):
                self.globals[k] = v

        return result if result is not None else 0

    def _builtin_print(self, *args) -> int:
        """打印 — 模拟翰语的 打印 函数"""
        parts = []
        for a in args:
            if isinstance(a, list):
                parts.append(self._format_list(a))
            elif isinstance(a, bool):
                parts.append("真" if a else "假")
            else:
                parts.append(str(a))
        self.output.append(" ".join(parts))
        return 0

    def _builtin_print_str(self, *args) -> int:
        """打印字符串"""
        self.output.append(" ".join(str(a) for a in args))
        return 0

    def _format_list(self, lst: list) -> str:
        """格式化列表输出"""
        items = []
        for item in lst:
            if isinstance(item, list):
                items.append(self._format_list(item))
            else:
                items.append(str(item))
        return "[" + " ".join(items) + "]"

    def _mangle(self, name: str) -> str:
        """标识符名称规范化"""
        return name


class _ReturnSignal:
    def __init__(self, value=None):
        self.value = value

class _BreakSignal:
    pass

class _ContinueSignal:
    pass


def run_source(source: str, source_path: str | None = None) -> tuple[str, str, int]:
    """编译并执行翰语源代码

    Returns: (stdout, stderr, exit_code)
    """
    # 确保 hanyu 包可导入
    hanyu_dir = os.environ.get("HANYU_DIR", "")
    if hanyu_dir and os.path.isdir(os.path.join(hanyu_dir, "src")):
        sys.path.insert(0, os.path.join(hanyu_dir, "src"))

    try:
        from hanyu.compiler import compile_source
    except ImportError:
        return ("", "无法导入翰语编译器（hanyu 包未安装）", 1)

    ir, ast, tokens, error = compile_source(source, source_path=source_path)
    if error:
        return ("", f"编译错误: {error}", 1)

    # 优先尝试原生执行（JIT/lli/clang）
    if ir:
        native = _try_native_execute(ir)
        if native is not None:
            return native

    # 回退到 Python AST 解释器
    if ast:
        interp = _HanyuInterpreter()
        stdout = interp.run(ast)
        return (stdout, "", 0)

    return ("", "无法执行：既无 IR 也无 AST", 1)


def main():
    """CLI 入口: python -m yanpub.adapters.hanyu.runner <file.翰>"""
    import argparse
    parser = argparse.ArgumentParser(description="翰语代码执行器")
    parser.add_argument("file", help="翰语源文件（.翰），或 - 表示从 stdin 读取")
    args = parser.parse_args()

    if args.file == "-":
        source = sys.stdin.read()
        source_path = None
    else:
        if not os.path.isfile(args.file):
            print(f"文件不存在: {args.file}", file=sys.stderr)
            sys.exit(1)
        source = open(args.file, encoding="utf-8").read()
        source_path = args.file

    stdout, stderr, rc = run_source(source, source_path)
    if stdout:
        sys.stdout.write(stdout)
        if not stdout.endswith("\n"):
            sys.stdout.write("\n")
    if stderr:
        sys.stderr.write(stderr + "\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
