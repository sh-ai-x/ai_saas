"""lib/babysit_pr_reliability.py — lock helpers for bin/babysit-pr-local.sh.

Three primitives the wrapper script imports via inline `python3 -c`:

  * is_stale_lock(path)            -> True if mtime > 1800s OR recorded PID gone
  * read_pr_lock_body(path)        -> str (file contents) or "" on read failure
  * try_acquire_pr_lock(path, body) -> True iff atomic mkdir of sibling
                                       `${path}.d` succeeded AND body was
                                       written to `path` (POSIX mkdir
                                       guarantees atomicity across processes).

The atomic acquisition is the load-bearing part — without it two
concurrent babysit sessions on the same PR can both pass an `[[ -f ]]`
check before either writes, producing interleaved log writes and
possibly conflicting pushes (TOCTOU race flagged in PR #766).
"""
from __future__ import annotations

import os
import re
import time

TTL_SECONDS = 1800  # stale-lock TTL per babysit-pr skill docs
PID_RE = re.compile(r"pid=(\d+)")


def is_stale_lock(path: str) -> bool:
    """True when the lock at `path` is stale (TTL exceeded OR recorded PID gone)."""
    try:
        mtime = os.path.getmtime(path)
    except FileNotFoundError:
        return False  # no lock = not stale; caller treats absence as "acquire me"
    if time.time() - mtime > TTL_SECONDS:
        return True
    try:
        with open(path, "r") as f:
            content = f.read()
    except OSError:
        return False  # unreadable = don't auto-stomp; let caller surface it
    m = PID_RE.search(content)
    if not m:
        return False
    pid = int(m.group(1))
    try:
        os.kill(pid, 0)  # signal 0 = existence check, no actual signal
    except ProcessLookupError:
        return True  # dead PID = stale
    except PermissionError:
        return False  # alive but owned by another user (don't claim)
    return False


def read_pr_lock_body(path: str) -> str:
    """Return the lock body, or '' on read failure (caller falls back to '<unreadable>')."""
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError:
        return ""


def try_acquire_pr_lock(path: str, body: str) -> bool:
    """Atomically acquire the lock at `path`. Returns True on success.

    Strategy: mkdir of the sibling `${path}.d` directory is the atomic
    primitive (POSIX guarantees a single mkdir either creates the dir or
    fails with EEXIST — never both). If mkdir succeeds we own the lock;
    write the body and return True. If mkdir fails the dir already
    exists; another process holds the lock; return False.
    """
    dir_path = f"{path}.d"
    try:
        os.mkdir(dir_path)
    except FileExistsError:
        return False
    except OSError:
        return False
    try:
        with open(path, "w") as f:
            f.write(body)
    except OSError:
        # Roll back the mkdir so a future attempt isn't blocked.
        try:
            os.rmdir(dir_path)
        except OSError:
            pass
        return False
    return True


if __name__ == "__main__":
    import sys
    import tempfile

    def _check(label: str, got: object, want: object) -> None:
        ok = got == want
        sys.stdout.write(f"  [{'OK' if ok else 'FAIL'}] {label}: got={got!r} want={want!r}\n")
        if not ok:
            sys.exit(1)

    with tempfile.TemporaryDirectory() as td:
        lock = os.path.join(td, "x.lock")
        # 1) acquire on empty dir (use self-PID so the lock looks alive)
        self_pid = os.getpid()
        _check("acquire fresh", try_acquire_pr_lock(lock, f"pid={self_pid} branch=test"), True)
        # 2) re-acquire while held -> False
        _check("acquire while held", try_acquire_pr_lock(lock, "pid=88888 branch=test"), False)
        # 3) read body
        _check("read body", read_pr_lock_body(lock).strip(), f"pid={self_pid} branch=test")
        # 4) not stale (just written, alive PID via self)
        _check("is_stale fresh", is_stale_lock(lock), False)
        # 5) stale by dead PID (use a clearly-dead large number)
        with open(lock, "w") as f:
            f.write("pid=999999999 branch=test")
        _check("is_stale dead-pid", is_stale_lock(lock), True)
        # 6) acquire fails on held lock
        _check("acquire on held (dead-pid)", try_acquire_pr_lock(lock, "pid=1 branch=test"), False)
        # 7) after releasing the .d dir, acquire succeeds
        os.rmdir(lock + ".d")
        os.remove(lock)
        _check("acquire after release", try_acquire_pr_lock(lock, "pid=1 branch=test"), True)
        # 8) stale by mtime > TTL_SECONDS (backdate the file)
        old = time.time() - TTL_SECONDS - 60
        os.utime(lock, (old, old))
        _check("is_stale old-mtime", is_stale_lock(lock), True)
    sys.stdout.write("babysit_pr_reliability: all checks passed\n")
