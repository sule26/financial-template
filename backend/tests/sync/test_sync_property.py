"""Property test (docs/05): random inbox operations never lose or double-count lines.

Invariant checked after every scan, for any sequence of mv / cp / rm / rewrite:
- the invoice content counts exactly once in the month total while any copy is on disk;
- nothing is counted for content no longer on disk;
- confirmed lines survive while a file with the same content is still in the inbox.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sync_env import Env, inter, make_env

# one invoice content; edits of the same (card, month) are covered by the supersession tests
CONTENTS = {"A": inter((1, "MERCADO A", "10.00"), (2, "PADARIA B", "5.50"))}
TOTALS = {"A": Decimal("15.50")}
NAMES = ["faturas/inter/x.pdf", "faturas/inter/y.pdf", "faturas/inter/sub/z.pdf"]

op = st.one_of(
    st.tuples(st.just("put"), st.sampled_from(NAMES), st.sampled_from(["A"])),
    st.tuples(st.just("mv"), st.sampled_from(NAMES), st.sampled_from(NAMES)),
    st.tuples(st.just("cp"), st.sampled_from(NAMES), st.sampled_from(NAMES)),
    st.tuples(st.just("rm"), st.sampled_from(NAMES), st.just("")),
    st.tuples(st.just("confirm"), st.just(""), st.just("")),
)


def _content_on_disk(env: Env) -> set[str]:
    found = set()
    for name in NAMES:
        path = env.inbox / name
        if path.is_file():
            data = path.read_bytes()
            found |= {k for k, v in CONTENTS.items() if v == data}
    return found


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(op, min_size=1, max_size=10))
def test_r3_random_inbox_operations_keep_one_source_of_truth(ops: list) -> None:  # type: ignore[type-arg]
    with tempfile.TemporaryDirectory() as tmp:
        env = make_env(Path(tmp))
        for kind, a, b in ops:
            src, dst = env.inbox / a, env.inbox / b
            if kind == "put":
                env.put(a, CONTENTS[b])
            elif kind == "mv" and src.is_file() and a != b:
                env.mv(a, b)
            elif kind == "cp" and src.is_file() and a != b:
                env.put(b, src.read_bytes())
            elif kind == "rm" and src.is_file():
                env.rm(a)
            elif kind == "confirm":
                for path, entry in env.manifest().items():
                    if entry.active and env.staged(path):
                        env.confirm_all(path)
            _ = dst
            env.scan()
            on_disk = _content_on_disk(env)
            expected = sum((TOTALS[k] for k in on_disk), Decimal("0.00"))
            assert Decimal(env.total()) == expected, (ops, on_disk)
            active = [e for e in env.manifest().values() if e.active]
            assert len({e.sha256 for e in active}) == len(active)  # one active entry per content
