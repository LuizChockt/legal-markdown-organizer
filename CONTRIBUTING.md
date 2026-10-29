# Contributing

Keep changes focused and include a small synthetic example of the behavior being changed.

1. Use Python 3.11 or newer and a virtual environment.
2. Install development dependencies with `python -m pip install -e ".[dev]"`.
3. Run `python -m pytest` from the repository root.
4. Include a regression test for a behavior change and update relevant documentation.
5. Open a pull request describing the problem, resulting behavior and commands run.

The [README](README.md) includes environment commands for Windows, Linux and macOS.
Run examples against synthetic data or disposable copies. Never include client files,
personal vaults, credentials, real case identifiers or confidential terminal output.
Report security issues through the process in [SECURITY.md](SECURITY.md).
