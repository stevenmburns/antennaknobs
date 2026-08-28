"""The antennaknobs → momwire private-import boundary (issue #932).

antennaknobs is momwire's biggest consumer, so it is the codebase most able
to quietly grow a dependency on a momwire name that momwire is free to
rename. #932 caught one of those: `web/adapter.py` imported
`array_block._wire_to_element` when `array_block.wire_to_element` — the
public name it is a plain alias of — was right there.

This test pins the whole boundary rather than that one site. It fails on

* a NEW private reach-through (someone adds `from momwire.x import _y`), and
* a STALE allowlist entry (a reach-through that was removed but left listed),

so the allowlist below stays an accurate census of the debt rather than
drifting into a rubber stamp.

Two categories are deliberately distinguished, because only one is a smell:

* **Compatibility re-exports** (`network.py`, `network_reduce.py`) — names
  that were importable from these modules before the `momwire.networks` move
  (momwire#456 ws2 phase B) and are re-exported so the ~40 design modules and
  ~50 test modules importing through them did not have to churn. Deliberate,
  documented in place, and removable only when momwire promotes public
  equivalents. `tests/test_networks_shim.py` owns their behavioural contract.
* **Incidental reach-throughs** (`builder.py`) — a caller that wanted a
  helper and took the private path to it. These are the ones worth retiring;
  each needs a public momwire name to land first.

Adding a line here is not forbidden — it is a deliberate act that says the
private path is the only one available. If a public equivalent exists, use it.
"""

import ast
import pathlib


SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "antennaknobs"

# (module path relative to src/antennaknobs, momwire module, imported name)
ALLOWED = {
    # Incidental reach-throughs: no public momwire equivalent today.
    ("builder.py", "momwire._ground_refl", "eps_tilde"),
    ("builder.py", "momwire._sommerfeld_below", "lambda_medium"),
    # Compatibility re-exports (momwire#456 ws2 phase B) — see module docstrings.
    ("network.py", "momwire.networks._reduce", "_series_rlc_impedance"),
    ("network.py", "momwire.networks._spec", "_branch_port_refs"),
    ("network.py", "momwire.networks._spec", "_parallel_rlc_admittance"),
    ("network.py", "momwire.networks._spec", "_rewrite_branch"),
}


def _is_private_momwire(module: str, name: str) -> bool:
    """True when the import reaches a private momwire module or private name."""
    if module.split(".")[0] != "momwire":
        return False
    return any(c.startswith("_") for c in module.split(".")) or name.startswith("_")


def _scan() -> set[tuple[str, str, str]]:
    found = set()
    for path in sorted(SRC.rglob("*.py")):
        rel = str(path.relative_to(SRC))
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            # `from momwire... import name` — level 0 only; a relative import
            # cannot reach momwire from inside antennaknobs.
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    if _is_private_momwire(node.module, alias.name):
                        found.add((rel, node.module, alias.name))
            # `import momwire._private [as x]`
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_private_momwire(alias.name, ""):
                        found.add((rel, alias.name, "<module>"))
    return found


FOUND = _scan()


def _fmt(entries):
    return "\n".join(
        f"  {rel}: from {mod} import {name}" for rel, mod, name in sorted(entries)
    )


def test_no_new_private_momwire_import():
    extra = FOUND - ALLOWED
    assert not extra, (
        "New private momwire reach-through(s):\n"
        + _fmt(extra)
        + "\n\nPrefer a public momwire name if one exists (issue #932 was exactly"
        " this: array_block._wire_to_element is a plain alias of the public"
        " array_block.wire_to_element).\nIf the private path really is the only"
        " one, add the entry to ALLOWED in this file with a one-line reason."
    )


def test_allowlist_has_no_stale_entry():
    stale = ALLOWED - FOUND
    assert not stale, (
        "ALLOWED lists import(s) that no longer exist:\n"
        + _fmt(stale)
        + "\n\nDelete them — the allowlist is a census, not a rubber stamp."
    )


def test_the_scanner_actually_finds_things():
    """A scanner that silently matched nothing would make both tests above
    pass vacuously once ALLOWED were emptied. Pin that it sees the real tree."""
    assert FOUND, "scanner found no private momwire imports at all — is SRC right?"
    assert SRC.is_dir() and (SRC / "network.py").exists()


def test_the_adapter_uses_the_public_wire_to_element():
    """The specific regression #932 fixed, pinned directly."""
    import momwire.array_block as ab

    assert ab.wire_to_element is ab._wire_to_element, (
        "momwire changed the alias; re-check what the adapter should import"
    )
    adapter = (SRC / "web" / "adapter.py").read_text()
    assert "import _wire_to_element" not in adapter
    assert "from momwire.array_block import wire_to_element" in adapter
