# -*- coding: utf-8 -*-
"""Sandbox guard: while tests run, block the three ways a test can touch
production - writing under a production folder, calling a production endpoint,
launching a production process - and count every attempt.

Before relying on it, release canaries: deliberately do each forbidden thing
once and require that every one is caught. A guard that was never tested is a
guard you only think you have.

    with SandboxGuard(production_roots=["/srv/live"],
                      production_endpoints=["127.0.0.1:9000"],
                      production_commands=["live-daemon"]) as guard:
        assert guard.release_canaries()["caught"] == 3
        ...  # code under test
    print(guard.report())

What it covers: open() / io.open() / pathlib.Path.open() in a write mode
(so Path.write_text and write_bytes too), plus explicit check_endpoint() /
check_launch() calls from the code under test.
What it does not cover: os.remove / os.rename, subprocess, sockets opened
without going through check_*. The point is the pattern - block, count, prove
with canaries - not a complete jail.
"""
import builtins
import io
import os
import pathlib
from pathlib import Path


class ProductionTouch(RuntimeError):
    """Raised in block mode when the code under test tries to touch production."""


_WRITE_MODES = set("wax+")


class SandboxGuard:
    def __init__(self, production_roots=(), production_endpoints=(), production_commands=(), mode="block"):
        if mode not in ("block", "record"):
            raise ValueError("mode must be 'block' or 'record'")
        self.roots = [Path(r).resolve() for r in production_roots]
        self.endpoints = set(production_endpoints)
        self.commands = set(production_commands)
        self.mode = mode
        self.counts = {"blocked_writes": 0, "blocked_endpoints": 0, "blocked_launches": 0, "allowed_writes": 0}
        self.log = []
        self.canaries = {"released": 0, "caught": 0}
        self._orig_open = None
        self._orig_path_open = None
        self._nested = False  # Path.open on 3.11+ calls io.open again; count once

    # classification ---------------------------------------------------------
    def is_production_path(self, path) -> bool:
        try:
            p = Path(os.fspath(path)).resolve()
        except (TypeError, OSError):
            return False
        return any(p == root or root in p.parents for root in self.roots)

    def _hit(self, counter: str, what: str) -> None:
        self.counts[counter] += 1
        self.log.append(f"{counter}: {what}")
        if self.mode == "block":
            raise ProductionTouch(what)

    # the three doors ----------------------------------------------------------
    def _check_write(self, file, mode) -> None:
        if _WRITE_MODES & set(mode) and not isinstance(file, int):
            if self.is_production_path(file):
                self._hit("blocked_writes", f"write to {os.fspath(file)}")
            else:
                self.counts["allowed_writes"] += 1

    def _guarded_open(self, file, mode="r", *args, **kwargs):
        if not self._nested:
            self._check_write(file, mode)
        return self._orig_open(file, mode, *args, **kwargs)

    def _guarded_path_open(self, path, mode="r", *args, **kwargs):
        self._check_write(path, mode)
        self._nested = True
        try:
            return self._orig_path_open(path, mode, *args, **kwargs)
        finally:
            self._nested = False

    def check_endpoint(self, hostport: str) -> None:
        if hostport in self.endpoints:
            self._hit("blocked_endpoints", f"call to {hostport}")

    def check_launch(self, argv) -> None:
        name = Path(str(argv[0])).name if argv else ""
        if name in self.commands:
            self._hit("blocked_launches", f"launch of {name}")

    # lifecycle ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self._orig_open is not None

    def __enter__(self):
        self._orig_open = builtins.open
        self._orig_path_open = pathlib.Path.open
        builtins.open = self._guarded_open
        io.open = self._guarded_open
        guard = self
        pathlib.Path.open = lambda p, mode="r", *a, **k: guard._guarded_path_open(p, mode, *a, **k)
        return self

    def __exit__(self, *exc):
        builtins.open = self._orig_open
        io.open = self._orig_open
        pathlib.Path.open = self._orig_path_open
        self._orig_open = None
        self._orig_path_open = None
        return False

    # canaries ---------------------------------------------------------------------
    def release_canaries(self) -> dict:
        """Try each forbidden action once; every attempt must be caught.
        Counts from the canaries are rolled back so the report shows only real attempts."""
        if not self.active:
            raise RuntimeError("guard is not active; release canaries inside the 'with' block")
        before = dict(self.counts)
        attempts = []
        for root in self.roots:
            attempts.append(lambda root=root: open(root / "__canary__.tmp", "w"))
        for ep in self.endpoints:
            attempts.append(lambda ep=ep: self.check_endpoint(ep))
        for cmd in self.commands:
            attempts.append(lambda cmd=cmd: self.check_launch([cmd]))
        caught = 0
        for attempt in attempts:
            try:
                attempt()
            except ProductionTouch:
                caught += 1
        self.canaries = {"released": len(attempts), "caught": caught}
        self.counts = before
        return dict(self.canaries)

    @property
    def armed(self) -> bool:
        return self.canaries["released"] > 0 and self.canaries["caught"] == self.canaries["released"]

    def report(self) -> str:
        c = self.counts
        return (f"mode {self.mode} | canaries {self.canaries['caught']}/{self.canaries['released']} caught | "
                f"production attempts: writes {c['blocked_writes']}, endpoints {c['blocked_endpoints']}, "
                f"launches {c['blocked_launches']} | sandbox writes allowed {c['allowed_writes']}")
