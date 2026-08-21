# Examples

## Real reference projects

Click and Cookiecutter are checked out at pinned upstream commits rather than vendored into this repository:

```bash
python examples/setup_reference_projects.py
python examples/setup_reference_projects.py --check
```

Their full Python 3.12 suites were executed through sealed Achilles-AI plans. See [REFERENCE_RESULTS.md](REFERENCE_RESULTS.md) for commands, evidence IDs, test counts, timing, and the Windows watchdog integrity caveat.

## Small verdict fixtures

Run the synthetic PASS, FAIL, and UNKNOWN fixtures from the project root after installing the package, or with `PYTHONPATH=src`:

```bash
python -B examples/run_demos.py
```

The runner uses temporary copies so evidence does not alter the fixtures. `pass_cli` and `fail_cli` execute the same black-box test; `unknown_cli` intentionally has no reliable automatic oracle.
