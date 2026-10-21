from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

# Each of these encodes a real past failure somewhere: they catch the classes of
# mistake that pass every other gate and then fail in production.

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
STATIC = APP / "mcp_stock_markets" / "static"


def helper_committed_text_files() -> list[Path]:
    """Every text file a person wrote, found by walking rather than by asking
    git, so the check also runs where git is absent."""
    skipped = {".git", ".venv", "__pycache__", ".ruff_cache", ".mypy_cache", ".pytest_cache"}
    kept = (".md", ".py", ".js", ".html", ".css", ".yml", ".yaml", ".toml", ".sh", ".txt", ".conf", ".json", ".svg")
    result = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in kept:
            continue
        if skipped & set(path.relative_to(ROOT).parts):
            continue
        result.append(path)
    return result


def helper_imports(nodes: list[ast.AST]) -> set[str]:
    result: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            result.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            result.update(alias.asname or alias.name for alias in node.names)
    return result


def helper_function_level_imports(tree: ast.Module) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            result |= helper_imports(list(ast.walk(node)))
    return result


def helper_scripts() -> str:
    return "".join(path.read_text(encoding="utf-8") for path in sorted(STATIC.glob("*.js")))


def test_lint__no_undefined_redefined_or_unused_names() -> None:
    """A missing import once caused a completely silent production failure."""
    result = subprocess.run(
        ["ruff", "check", "--select", "F821,F811,F841", "--quiet", APP.as_posix()],
        capture_output=True,
        text=True,
        check=False,
    )
    expected = (0, "")
    assert (result.returncode, result.stdout) == expected


def test_module_hygiene__every_module_parses_and_nothing_is_shadowed() -> None:
    """A function-level import shadowing a module-level one works until the two diverge."""
    result: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        clash = helper_imports(list(tree.body)) & helper_function_level_imports(tree)
        if clash:
            result.append(f"{path.relative_to(ROOT).as_posix()}: {sorted(clash)}")
    expected: list[str] = []
    assert result == expected


def test_frontend__no_id_is_declared_twice() -> None:
    ids = re.findall(r'\bid="([^"]+)"', (STATIC / "index.html").read_text(encoding="utf-8"))
    result = sorted({name for name in ids if ids.count(name) > 1})
    expected: list[str] = []
    assert result == expected


def test_frontend__every_element_the_script_reaches_for_exists() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    declared = set(re.findall(r'\bid="([^"]+)"', html))
    reached = set(re.findall(r"""(?:\$|querySelector)\(["']#([\w-]+)["']""", helper_scripts()))
    result = sorted(reached - declared)
    expected: list[str] = []
    assert result == expected


def test_frontend__every_view_the_script_opens_exists() -> None:
    """A view named in the script but missing from the page shows nothing at all."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    declared = set(re.findall(r'data-view="([\w-]+)"', html))
    named = set(re.findall(r'(?:shown|opened)\("([\w-]+)"\)', script))
    named |= set(re.findall(r'"([\w-]+)"', script.split("const VIEWS = [")[1].split("]")[0]))
    named |= set(re.findall(r'data-nav="([\w-]+)"', html))
    result = sorted(named - declared)
    expected: list[str] = []
    assert result == expected


def test_frontend__no_native_dialog_and_strict_equality() -> None:
    """In-app modals only, and `===` / `!==` only."""
    result: list[str] = []
    for path in sorted(STATIC.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\b(alert|confirm|prompt)\(", text):
            result.append(f"{path.name}: native dialog")
        if re.search(r"[^=!]==[^=]|!=[^=]", text):
            result.append(f"{path.name}: loose equality")
    expected: list[str] = []
    assert result == expected


def test_frontend__no_inline_script_and_no_cdn() -> None:
    """The CSP is `script-src 'self'`, and nothing loads from elsewhere."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    inline_handlers = re.findall(r"\son[a-z]+=", html)
    remote = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    result = (inline_scripts, inline_handlers, remote)
    expected: tuple[list[str], list[str], list[str]] = ([], [], [])
    assert result == expected


def test_frontend__theme_is_set_before_the_first_paint() -> None:
    """`theme.js` runs in <head>, without defer or async, ahead
    of the stylesheet — a deferred one paints the light theme first."""
    head = (STATIC / "index.html").read_text(encoding="utf-8").split("</head>")[0]
    theme_tag = re.search(r'<script src="/static/theme\.js\?v=__BUILD__"></script>', head)
    stylesheet = head.find('rel="stylesheet"')
    result = (theme_tag is not None, theme_tag is not None and theme_tag.start() < stylesheet)
    expected = (True, True)
    assert result == expected


def test_docs__no_conversation_markup_in_anything_committed() -> None:
    """An agent once pasted the tail of its own tool call into a committed
    audit. The markers are split so this file does not trip on itself."""
    markers = ("</" + "invoke>", "</" + "content>", "<function" + "_calls", "[SYS" + "TEM")
    result: list[str] = []
    for path in helper_committed_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(marker in text for marker in markers):
            result.append(path.relative_to(ROOT).as_posix())
    expected: list[str] = []
    assert result == expected


def test_docs__nothing_personal_in_a_public_repository() -> None:
    """The repository is public: no real address, no server, no domain of the
    owner's. Only example addresses (example.com, RFC 5737's documentation
    networks) and the loopback appear; the markers are split so this file
    does not trip on itself."""
    owner_domain = "edgy" + ".world"
    allowed_addresses = ("127.0.0.1", "0.0.0.0", "192.0.2.", "198.51.100.", "203.0.113.")
    result: list[str] = []
    for path in helper_committed_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        addresses = {
            address
            for address in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
            if not address.startswith(allowed_addresses)
        }
        # A URL's credentials (user:password@host) are not an email address.
        emails = {
            email
            for email in re.findall(r"(?<![\w:/])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
            if not email.lower().endswith("example.com") and not email.split("@")[1][0].isdigit()
        }
        if owner_domain in text or addresses or emails:
            result.append(path.relative_to(ROOT).as_posix())
    expected: list[str] = []
    assert result == expected
