"""Locating a user-supplied engine binary — shared by the NEC-5 and NEC-2 wrappers.

Both wrappers drive an executable antennaknobs never ships: NEC-5 because it is
licensed (#825), NEC-2 because bundling one would make the zip a GPL combined
work (#1354). The question "where is it" has the same two answers in both cases
— an explicit path from the caller, else an environment variable — and the same
two non-answers, which is why this is one function rather than two.

The distinction the return value draws is deliberate and is the reason a bare
`os.environ.get` will not do: **None means "no binary here", never "the variable
was empty"**, so a variable pointing at a directory, a missing file or a
non-executable is an absence rather than a path a caller will later fail to
run. What None does NOT mean is "this is the wrong program" — that needs a run,
and each wrapper's own probe is where that lives (`probe_nec5`, `probe_nec2`).
"""

from __future__ import annotations

import os
import subprocess
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


def find_exe(env_var: str, explicit: str | None = None) -> str | None:
    """The executable named explicitly, else by ``$env_var``, else by the
    settings file's ``[engines]`` table (AK#1492); None if none resolves to an
    executable file."""
    from ..settings_file import engine_exe

    cand = explicit or os.environ.get(env_var) or engine_exe(env_var)
    if not cand:
        return None
    p = Path(cand).expanduser()
    if p.is_file() and os.access(p, os.X_OK):
        return str(p)
    return None


# The cancel token of the solve this thread is running, if any (AK#1712).
#
# An external engine is a child process, so the momwire token the server's
# lane hands a solve cannot reach it through a kernel checkpoint. Threading a
# `cancel=` argument down through every backend, adapter and engine method
# that can end in a deck run would touch dozens of signatures for one poll
# loop at the bottom, so the server binds the token for the duration of the
# call instead (`cancel_scope`) and `run_exe` — the one place a binary is
# launched — reads it. A context variable, not a global: each threadpool
# worker runs its own solve, and a token must never reach another session's
# process.
_CANCEL: ContextVar = ContextVar("antennaknobs_engine_cancel", default=None)

# How often a running binary checks its token. The cost is one wakeup; the
# benefit bounds how long a cancelled NEC-5 fill keeps a core.
_POLL_S = 0.1


@contextmanager
def cancel_scope(token):
    """Bind ``token`` (anything with a ``cancelled`` flag, normally a
    ``momwire.CancelToken``) as the cancel for every binary launched inside
    the block on this thread. ``None`` is accepted and binds nothing."""
    reset = _CANCEL.set(token)
    try:
        yield
    finally:
        _CANCEL.reset(reset)


def run_exe(
    argv: list[str], *, stdin_text: str, cwd: str, timeout: float
) -> subprocess.CompletedProcess:
    """``subprocess.run(argv, input=stdin_text, text=True, capture_output=True, ...)``
    that also dies with the solve that asked for it.

    With no token bound this IS ``subprocess.run`` (the availability probes,
    the CLI). With one bound, the process is polled every ``_POLL_S`` and
    killed the moment the token trips, raising ``momwire.SolveAborted`` — the
    same exception a cancelled momwire solve raises, so every caller's abort
    handling applies unchanged. ``timeout`` keeps ``subprocess.run``'s
    meaning, ``TimeoutExpired`` included.
    """
    token = _CANCEL.get()
    if token is None:
        return subprocess.run(
            argv,
            input=stdin_text,
            text=True,
            capture_output=True,
            cwd=cwd,
            timeout=timeout,
        )
    import momwire

    if token.cancelled:
        raise momwire.SolveAborted()
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    ) as proc:
        pending_input: str | None = stdin_text
        while True:
            try:
                out, err = proc.communicate(pending_input, timeout=_POLL_S)
                break
            except subprocess.TimeoutExpired:
                # communicate() refuses input once it has started; the first
                # call already handed it over.
                pending_input = None
            if token.cancelled:
                proc.kill()
                proc.communicate()
                raise momwire.SolveAborted()
            if time.monotonic() >= deadline:
                proc.kill()
                out, err = proc.communicate()
                raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)
