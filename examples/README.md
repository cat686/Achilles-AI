# Demo fixtures

Run all fixtures from the project root after installing the package, or with `PYTHONPATH=src`:

```bash
python -B examples/run_demos.py
```

The runner uses temporary copies so demo evidence does not alter the checked-in fixtures. `pass_cli` and `fail_cli` execute real black-box tests; `unknown_cli` intentionally has no reliable automatic oracle.

