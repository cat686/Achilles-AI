# Demo fixtures

Run all fixtures from the project root after installing the package, or with `PYTHONPATH=src`:

```bash
python -B examples/run_demos.py
```

The runner uses temporary copies so demo evidence does not alter the checked-in fixtures. Each fixture follows `init → seal → run/report`; `pass_cli` and `fail_cli` execute a sealed black-box test and `unknown_cli` intentionally has no reliable automatic oracle.
