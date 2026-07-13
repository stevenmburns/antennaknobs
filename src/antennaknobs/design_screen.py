"""Static advisory screening for user-authored design files.

A user design is loaded with ``exec_module`` (see ``user_designs.load_builder``)
— it runs with your full user privileges, exactly like any script, macro, or
editor plugin. Full Python is a deliberate feature (you need the whole language
to describe an antenna), so this module does NOT try to sandbox or veto code.
It AST-parses a candidate file *without executing it* and reports what a design
does that a *typical* one doesn't — imports outside ``antennaknobs`` and the
scientific standard library, ``eval``/``exec``, file/network/process access, or
interpreter-introspection escapes.

This is an **advisory**, not a security boundary. It informs the trust decision
(see ``design_trust``): "before you trust this file, note that it opens files
and imports ``subprocess``." It is DETECTION, not prevention — a determined
attacker can obfuscate past an AST scan, and an allow-listed library like numpy
has file-I/O and pickle corners (``numpy.load(allow_pickle=True)``) an attribute
scan won't fully cover. You cannot make ``exec`` of arbitrary Python safe from
inside the interpreter; real containment needs process/VM/WASM isolation. What
this reliably does is surface the obvious so a human's trust decision is
informed rather than blind.

The allow-list is the same contract the built-in designs follow ("only import
from ``antennaknobs`` and the standard library"), so every shipped design
screens clean and a flagged *user* file is doing something unusual worth a
glance — not necessarily something malicious.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Finding",
    "ScreenReport",
    "screen_source",
    "screen_file",
]

# Import roots a legitimate design may use: the package itself plus the
# math/scientific standard library the built-in catalog draws on. Anything not
# listed here is reported (as "unrecognized", MEDIUM) rather than silently
# allowed — default-deny, but with a softer message than the known-dangerous
# modules below so the human can tell "unusual" from "alarming".
_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "antennaknobs",
        "__future__",
        "math",
        "cmath",
        "numpy",
        "scipy",
        "types",
        "typing",
        "typing_extensions",
        "dataclasses",
        "enum",
        "collections",
        "itertools",
        "functools",
        "operator",
        "decimal",
        "fractions",
        "statistics",
        "numbers",
        "string",
        "re",
        "copy",
        "abc",
        "warnings",
        "logging",
        # Benign data-format parsers. These operate on strings/iterables and
        # can't reach the filesystem on their own — getting a file to them
        # still needs raw open/pathlib, or the confined
        # antennaknobs.read_data/read_json helper.
        "json",
        "csv",
    }
)

# Modules whose mere import is alarming in a design file — the classic
# exfiltration / code-execution / persistence surface. Reported HIGH.
_DANGEROUS_IMPORT_ROOTS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "ctypes",
        "cffi",
        "importlib",
        "imp",
        "pickle",
        "marshal",
        "shelve",
        "urllib",
        "http",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "telnetlib",
        "multiprocessing",
        "threading",
        "_thread",
        "asyncio",
        "pty",
        "mmap",
        "fcntl",
        "resource",
        "signal",
        "tempfile",
        "pathlib",
        "glob",
        "fileinput",
        "inspect",
        "gc",
        "code",
        "codeop",
        "runpy",
        "builtins",
        "__builtin__",
        "platform",
        "getpass",
        "pwd",
        "grp",
        "crypt",
        "webbrowser",
        "setuptools",
        "distutils",
        "pip",
        "site",
        "atexit",
    }
)

# Bare builtins that read/write files, spawn, or compile+run code. HIGH.
_DANGEROUS_CALLS = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "input",
        "breakpoint",
        "exit",
        "quit",
    }
)

# Reflection builtins — benign with a constant attribute name, an escape hatch
# with a computed one. Flagged MEDIUM only when the attribute isn't a literal.
_REFLECTION_CALLS = frozenset({"getattr", "setattr", "delattr"})

# Namespace-introspection builtins. MEDIUM.
_NAMESPACE_CALLS = frozenset({"globals", "locals", "vars"})

# Dunder attributes that form the classic sandbox-escape gadget chains
# (``().__class__.__bases__[0].__subclasses__()`` and friends). These never
# appear in legitimate geometry math. HIGH. Deliberately excludes common,
# benign dunders like ``__class__``/``__dict__``/``__name__``.
_ESCAPE_ATTRS = frozenset(
    {
        "__globals__",
        "__subclasses__",
        "__bases__",
        "__base__",
        "__mro__",
        "__builtins__",
        "__code__",
        "__closure__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
        "__import__",
        "__loader__",
    }
)

# Bare names whose use implies reaching the interpreter internals. HIGH.
_DANGEROUS_NAMES = frozenset({"__builtins__", "__import__", "__loader__"})


@dataclass(frozen=True)
class Finding:
    """One screened-out construct. ``severity`` is ``"high"`` (a real antenna
    design never does this) or ``"medium"`` (unusual — worth a human glance)."""

    severity: str
    category: str
    message: str
    lineno: int
    col: int

    def __str__(self) -> str:
        return f"  line {self.lineno}: [{self.severity}] {self.message}"


@dataclass(frozen=True)
class ScreenReport:
    """Result of screening one file. ``blocked`` is True if anything was
    flagged; ``high``/``medium`` split the findings by severity."""

    filename: str
    findings: tuple[Finding, ...]

    @property
    def blocked(self) -> bool:
        return bool(self.findings)

    @property
    def high(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "high")

    @property
    def medium(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "medium")

    def summary(self) -> str:
        """A human-readable block listing every finding, for a trust prompt or
        a CLI message."""
        if not self.findings:
            return f"{self.filename}: nothing unusual — only geometry math."
        head = (
            f"{self.filename}: does things a typical antenna design doesn't "
            f"(worth a look before you trust it):"
        )
        body = "\n".join(str(f) for f in self.findings)
        return f"{head}\n{body}"


def _import_root(name: str | None) -> str | None:
    """Top-level package of a dotted module name (``a.b.c`` → ``a``)."""
    if not name:
        return None
    return name.split(".", 1)[0]


class _Screener(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def _add(self, severity: str, category: str, message: str, node: ast.AST) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                category=category,
                message=message,
                lineno=getattr(node, "lineno", 0),
                col=getattr(node, "col_offset", 0),
            )
        )

    def _check_import_root(self, root: str | None, node: ast.AST) -> None:
        if root in _ALLOWED_IMPORT_ROOTS:
            return
        if root in _DANGEROUS_IMPORT_ROOTS:
            self._add(
                "high",
                "import",
                f"imports {root!r} — file/network/process/system access, "
                f"which antenna geometry never requires",
                node,
            )
        else:
            self._add(
                "medium",
                "import",
                f"imports {root!r}, which is not part of the design API "
                f"(antennaknobs + the math standard library)",
                node,
            )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import_root(_import_root(alias.name), node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and node.level > 0:
            # Relative import: has no meaning for a path-loaded design (no
            # package context) and is off-contract regardless.
            self._add(
                "medium",
                "import",
                "uses a relative import; user designs must import absolutely "
                "from antennaknobs",
                node,
            )
        else:
            self._check_import_root(_import_root(node.module), node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
            if name in _DANGEROUS_CALLS:
                self._add(
                    "high",
                    "call",
                    f"calls {name}() — runs code or touches files/stdin, "
                    f"never needed to build antenna geometry",
                    node,
                )
            elif name in _REFLECTION_CALLS:
                # getattr(x, "const") is fine; getattr(x, expr) is the escape.
                attr_arg = node.args[1] if len(node.args) >= 2 else None
                is_const = isinstance(attr_arg, ast.Constant) and isinstance(
                    attr_arg.value, str
                )
                if not is_const:
                    self._add(
                        "medium",
                        "call",
                        f"calls {name}() with a computed attribute name — a "
                        f"common reflection escape hatch",
                        node,
                    )
            elif name in _NAMESPACE_CALLS:
                self._add(
                    "medium",
                    "call",
                    f"calls {name}() to reach the namespace dictionaries",
                    node,
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _ESCAPE_ATTRS:
            self._add(
                "high",
                "attribute",
                f"accesses {node.attr} — an interpreter-introspection escape "
                f"used to break out of restricted execution",
                node,
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in _DANGEROUS_NAMES:
            self._add(
                "high",
                "name",
                f"references {node.id} — reaches the interpreter internals",
                node,
            )
        self.generic_visit(node)


def screen_source(source: str, filename: str = "<design>") -> ScreenReport:
    """AST-screen design *source* without executing it.

    Raises ``SyntaxError`` if the source doesn't parse: an unparseable file
    can't be executed either, so the loader lets the native error surface (it
    names the line and reason the author needs) rather than the screener
    masking it. Screening only decides between *safe* and *dangerous*; it
    never decides *loadable*.
    """
    tree = ast.parse(source, filename=filename)  # SyntaxError propagates
    screener = _Screener()
    screener.visit(tree)
    # Stable order: by position in the file.
    findings = tuple(sorted(screener.findings, key=lambda f: (f.lineno, f.col)))
    return ScreenReport(filename=filename, findings=findings)


def screen_file(path: Path) -> ScreenReport:
    """AST-screen a design file by path without executing it."""
    source = Path(path).read_text(encoding="utf-8")
    return screen_source(source, filename=Path(path).name)
