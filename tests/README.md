# Regression strategies

The application ships only `examples/gpt61_sol_max_2027`. Historical strategy test data is maintained in Arena-Strategies, independently of the current published library.

```sh
git clone https://github.com/RM-Arena/Arena-Strategies.git .arena_data/strategy-tests
git -C .arena_data/strategy-tests checkout a2ee3ca3971e368a3ee8d598a0d90aa108539d66
uv run --locked python -m unittest discover -s tests
```

For a checkout elsewhere set `ARENA_STRATEGIES_SOURCE` to that path. Tests explicitly supply `RMUC_TEST_STRATEGIES` to catalogs and generators; normal application launches use only the bundled Sol Max example. Strategy generators other than Sol Max write to `build/strategy-repository/strategies` by default, or `RMUC_STRATEGY_OUTPUT` when supplied. Generated strategies must be submitted to Arena-Strategies.
