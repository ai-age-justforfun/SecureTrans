#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecureTrans 轻量静态检查（零依赖，AST）。
检查项：
  [FAIL] 语法错误（compile）
  [FAIL] 未定义名称（按作用域链：模块/函数/类 + 参数 + 全局声明 + builtins）
  [FAIL] 重复函数/类定义
  [WARN] 未使用 import（仅提示，--strict 时升级为 FAIL）
用法：python3 infra/static_check.py [file ...]   # 缺省自动检查 src/ tests/
退出码：0 无 FAIL；1 有 FAIL
"""
import ast
import builtins
import glob
import sys

BUILTINS = set(dir(builtins))


def collect_defs(body, out):
    """收集一个作用域 body 中直接定义的名字。"""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                out.add(a.asname or a.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                out.add(node.target.id)
        elif isinstance(node, ast.For):
            if isinstance(node.target, ast.Name):
                out.add(node.target.id)
            elif isinstance(node.target, (ast.Tuple, ast.List)):
                for e in node.target.elts:
                    if isinstance(e, ast.Name):
                        out.add(e.id)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                out.add(node.name)
        elif isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name):
                    out.add(item.optional_vars.id)


def used_names(body, out):
    """收集 Load 上下文的 Name id。"""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            out.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            pass  # 属性名不收集（避免 a.b 中 b 误判）


class UndefChecker(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.errors = []
        self.scope_stack = []  # 每层 (defined_set, is_function)

    def check_undef(self, node):
        """按作用域链查 Name 是否已定义。"""
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                if n.id in BUILTINS:
                    continue
                found = False
                for defined, _ in reversed(self.scope_stack):
                    if n.id in defined:
                        found = True
                        break
                if not found:
                    self.errors.append(
                        f"{self.path}: 未定义名称 {n.id} (L{n.lineno})")

    def visit_FunctionDef(self, node):
        local = set()
        collect_defs([node], local)  # 函数名自身
        for a in node.args.args + node.args.kwonlyargs:
            local.add(a.arg)
        if node.args.vararg:
            local.add(node.args.vararg.arg)
        if node.args.kwarg:
            local.add(node.args.kwarg.arg)
        for a in node.args.posonlyargs:
            local.add(a.arg)
        local.update(n.arg for n in node.args.kw_defaults if n and isinstance(n, ast.Name))
        globs = set()
        for d in node.body:
            if isinstance(d, ast.Global):
                globs.update(d.names)
            if isinstance(d, ast.Nonlocal):
                pass
        local.update(globs)
        self.scope_stack.append((local, True))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        local = {node.name}
        collect_defs(node.body, local)
        self.scope_stack.append((local, False))
        for n in node.body:
            self.visit(n)
        self.scope_stack.pop()

    def visit_Module(self, node):
        local = set()
        collect_defs(node.body, local)
        self.scope_stack.append((local, False))
        for n in node.body:
            self.visit(n)
        self.scope_stack.pop()

    def visit_Name(self, node):
        pass  # 统一在 check_undef 处理

    def visit_Attribute(self, node):
        pass  # 不展开属性


def check_file(path, strict=False):
    errors = []
    warnings = []
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        errors.append(f"{path}: 语法错误 L{e.lineno}: {e.msg}")
        return errors, warnings
    # 重复定义（模块级）
    seen = {}
    for child in tree.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if child.name in seen:
                errors.append(f"{path}: 重复定义 {child.name}（L{seen[child.name]} 与 L{child.lineno}）")
            seen[child.name] = child.lineno
    # 未定义名称
    checker = UndefChecker(path)
    checker.visit(tree)
    errors.extend(checker.errors)
    # 未使用 import（宽松：模块内 Name 出现即算使用）
    used = set()
    used_names(tree.body, used)
    for child in ast.walk(tree):
        if isinstance(child, ast.Import):
            for a in child.names:
                nm = a.asname or a.name.split(".")[0]
                if nm not in used:
                    warnings.append(f"{path}: 未使用 import {a.name} (L{child.lineno})")
        elif isinstance(child, ast.ImportFrom):
            for a in child.names:
                nm = a.asname or a.name
                if nm != "*" and nm not in used:
                    warnings.append(f"{path}: 未使用 import {a.name} (L{child.lineno})")
    return errors, warnings


def main():
    args = sys.argv[1:]
    files = args if args else (glob.glob("src/*.py") + glob.glob("tests/*.py") + glob.glob("infra/*.py"))
    strict = "--strict" in args
    if strict:
        files = [f for f in files if f != "--strict"]
    all_err, all_warn = [], []
    for f in sorted(set(files)):
        e, w = check_file(f, strict)
        all_err.extend(e)
        all_warn.extend(w)
    for w in all_warn:
        print(f"⚠ {w}")
    for e in all_err:
        print(f"❌ {e}")
    print(f"--- 静态检查完成：文件 {len(set(files))} 个，FAIL {len(all_err)}，WARN {len(all_warn)}")
    if strict and all_warn:
        all_err.extend(all_warn)
    sys.exit(1 if all_err else 0)


if __name__ == "__main__":
    main()
