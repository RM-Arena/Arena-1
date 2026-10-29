# Contributing

Arena-1 is source-available for **non-commercial learning only**. Read
[LICENSE](LICENSE) before using or contributing. Contributions remain under
the project's license; do not submit material you cannot license or redistribute.

1. Install Python 3.12, uv, Node.js 22+, Bun 1.3.14+ and stable Rust.
2. Run `python scripts/project.py setup` (`python3` on systems using that name).
3. Make a focused change on a branch. Preserve existing strategy interfaces,
   replay formats, robot models and rendering settings unless changing them is
   the explicit purpose of the contribution.
4. Run `python scripts/project.py test`, `bun run build`, `bun run docs:build`
   and `python scripts/check_release.py`.
5. For engine changes, test a seeded replay. For desktop changes, run
   `bun run desktop:dev --smoke-test` and verify exit cleans up the backend.
6. Open a pull request explaining the user-visible problem, change and tests.

Edit guide fragments under `docs/agent_guides/source/`, then regenerate with
`python scripts/build_agent_guides.py`; use `--check` in validation. Models
are generated from the Blender sources in `assets/blender/`. Do not commit
training tokens, private strategies, runtime registries, replays or build output.

CI tests native Windows, macOS and Linux. Docker isolation tests run separately
on Linux; local policy mode executes trusted code and is not a security sandbox.

Long-horizon strategy outcomes are a separate benchmark: run
`uv run python scripts/benchmark_strategy.py` or the manual **Strategy outcome
benchmark** workflow. The 80-second siege-route target passes on the current
macOS reference but has not passed on Linux; it is not a runtime portability
guarantee. Focused navigation and physical fly-slope tests remain in the normal
cross-platform suite. Do not change benchmark thresholds merely to hide a
strategy regression.

## Strategy contributions

Submit all new and updated strategies to [Arena-Strategies](https://github.com/RM-Arena/Arena-Strategies),
under `strategies/<season>/<provider>/<name>/`. Do not add strategy submissions to this repository's
`examples/`; it contains only the GPT-6.1-Sol-Max trident reference.
Regression strategy inputs live in the independent repository as well; see [tests/README.md](tests/README.md).
