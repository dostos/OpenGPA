"""Static-inspection test: every `realloc(...)` call in the GL shim C
sources must capture the return value into a temporary and NULL-check
before overwriting the previous pointer.

Catches the classic leak-and-crash pattern::

    p = realloc(p, n);   // if realloc returns NULL, `p` is leaked AND
                         // subsequent writes overrun the now-freed block.

We accept three "safe" patterns:

1. ``TYPE* tmp = realloc(old, n); if (!tmp) { ... } old = tmp;``
2. ``TYPE* nb = realloc(old, n); if (!nb) { ... }`` (followed by assign)
3. The realloc is inside a local wrapper that itself handles NULL
   (allowlisted by filename in :data:`ALLOWLIST_WRAPPERS`).

If you add a new realloc() that looks like the unsafe `foo = realloc(foo, n)`
pattern, this test fails. Fix the call site; don't allowlist it.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIM_DIRS = [REPO_ROOT / "src" / "shims" / "gl"]

# The unsafe pattern: `<ident> = ... realloc(<ident>, ...)`. Captured
# identifiers must match, i.e. we're reassigning the same pointer we're
# feeding into realloc. The assignment target may include struct-member
# access (`foo->bar`) — those are also at risk.
UNSAFE_RE = re.compile(
    r"""
    (?P<dst>                       # assignment target
       [A-Za-z_][\w\.\->\(\)\*\s]*? # ident, possibly with -> or .
    )
    \s*=\s*
    (?:\([^)]+\)\s*)?              # optional cast, e.g. (char*)
    realloc\s*\(\s*
    (?P<src>[A-Za-z_][\w\.\->\(\)\*\s]*?) # first arg
    \s*,
    """,
    re.VERBOSE,
)


def _strip_comments(src: str) -> str:
    # Remove /* ... */ (non-greedy) and // ...\n
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def _same_pointer(dst: str, src: str) -> bool:
    """Conservative equality: normalise whitespace and strip leading cast
    or unary `*`. Returns True iff dst and src refer to the same lvalue."""
    def norm(s: str) -> str:
        s = s.strip()
        # Kill trailing parens/whitespace, etc.
        return re.sub(r"\s+", "", s)
    return norm(dst) == norm(src)


def test_no_unsafe_realloc_reassignment_in_shim():
    offenders: list[str] = []
    for shim_dir in SHIM_DIRS:
        for src_file in shim_dir.rglob("*.c"):
            src = _strip_comments(src_file.read_text())
            for match in UNSAFE_RE.finditer(src):
                dst = match.group("dst")
                src_arg = match.group("src")
                if _same_pointer(dst, src_arg):
                    # Try to get the line number for readability.
                    line = src[: match.start()].count("\n") + 1
                    offenders.append(
                        f"{src_file.relative_to(REPO_ROOT)}:{line}: "
                        f"`{dst.strip()} = realloc({src_arg.strip()}, ...)` "
                        "— realloc return must be captured in a temp and NULL-checked"
                    )
    assert not offenders, (
        "Unsafe realloc-reassignment pattern detected — this leaks the old "
        "allocation on OOM and crashes on the next write.\n"
        + "\n".join(offenders)
    )
