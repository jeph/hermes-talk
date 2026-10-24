# Agent notes

This repository is jeph's fork of TheSmokeDev/hermes-talk. `FORK.md` lists every
intentional difference from upstream and the procedure for merging upstream.

- Before merging or cherry-picking from `upstream`, read `FORK.md` and keep each
  listed difference unless its "Drop when" condition is met.
- When you add, change, or remove a difference from upstream, update `FORK.md` in
  the same commit.
- Lint with `uvx ruff==0.17.1 check .` and test with `.venv/bin/python -m pytest -q`
  (create the venv with `uv venv --python 3.14 .venv && uv pip install --python .venv -e ".[dev]"`).
