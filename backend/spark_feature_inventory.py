"""Offline structural inventory of Python APIs; never imports or runs target code.

This module intentionally returns names and counts only, not source excerpts,
docstrings, comments, literals, or inferred feature success. It is appropriate
for local inspection of third-party code with restrictive redistribution terms.
"""
import ast
import os
from pathlib import Path

SKIP_DIRS = frozenset({'.git', '.svn', 'node_modules', '.venv', 'venv',
                       '__pycache__', 'dist', 'build', '.next', 'vendor', 'coverage'})
SENSITIVE_NAMES = ('secret', 'credential', 'token', 'password', 'private_key')


def inventory_python_symbols(root, *, max_files=300, max_symbols=1500,
                             max_file_bytes=65536):
    """Report bounded top-level classes/functions and public method names.

    No network, package installation, code execution or source-text export.
    Static names are *not* evidence of runtime correctness or safe execution.
    """
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Choose an existing, non-linked source directory.')
    if not (1 <= max_files <= 1000 and 1 <= max_symbols <= 10000
            and 128 <= max_file_bytes <= 1_048_576):
        raise ValueError('Inventory bounds are invalid.')
    root = root.resolve()
    modules = []
    parse_failures = 0
    symbols = 0
    inspected = 0
    truncated = False

    def visible(name):
        return not name.startswith('_') and len(name) <= 100

    def add_name(result, name):
        nonlocal symbols, truncated
        if not visible(name):
            return
        if symbols >= max_symbols:
            truncated = True
            return
        symbols += 1
        result.append(name)

    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not d.startswith('.') and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            file = Path(directory) / name
            if (not name.endswith('.py') or name.startswith('.') or
                    any(word in name.casefold() for word in SENSITIVE_NAMES) or
                    file.is_symlink()):
                continue
            if inspected >= max_files or symbols >= max_symbols:
                truncated = True
                break
            inspected += 1
            try:
                if file.stat().st_size > max_file_bytes:
                    continue
                source = file.read_text(encoding='utf-8-sig')
                tree = ast.parse(source, filename=name)
            except (OSError, UnicodeError, SyntaxError, ValueError, MemoryError):
                parse_failures += 1
                continue
            row = {'path': file.relative_to(root).as_posix(), 'classes': [], 'functions': []}
            for node in tree.body:
                if symbols >= max_symbols:
                    truncated = True
                    break
                if isinstance(node, ast.ClassDef) and visible(node.name):
                    if symbols >= max_symbols:
                        truncated = True
                        break
                    symbols += 1
                    cls = {'name': node.name, 'methods': []}
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            add_name(cls['methods'], child.name)
                    row['classes'].append(cls)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_name(row['functions'], node.name)
            modules.append(row)
        if truncated:
            break
    return {'version': 1, 'proof': 'static-symbols-only', 'runtime_verified': False,
            'parsed_files': len(modules), 'parse_failures': parse_failures,
            'inspected_files': inspected, 'symbol_count': symbols,
            'truncated': truncated, 'modules': modules}


def model_shareable_reference(evidence):
    """Conservatively gate model transmission of imported third-party source.

    Local paths are governed separately by the owner-provided source policy.
    Imported repositories must affirmatively have a detected permissive license.
    A permissive heuristic is not a substitute for legal review.
    """
    if not isinstance(evidence, dict):
        return False
    if 'imported' not in evidence:
        return True
    license_info = evidence.get('license')
    return isinstance(license_info, dict) and license_info.get('permissive') is True
