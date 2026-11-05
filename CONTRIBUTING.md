# Contributing

Use a runtime listed in `.github/workflows/ci.yml`. Install the development tools, then run:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.lock -e .
ruff check .
ruff format --check .
mypy --strict src
python -m pytest
python -m build
python -m twine check --strict dist/*
```

The test suite checks the README examples and conformance fixtures without credentials.
For live tests, set `THUNDER_API_KEY` from your own key file and set
`THUNDER_V1_BASE_URL` and `THUNDER_V2_BASE_URL` to the API endpoints:

```sh
THUNDER_INTEGRATION=1 python -m pytest tests/test_integration_info.py
```

Live tests may use quota. Never commit keys or slip data.
Keep pull requests focused, add regression tests and update both READMEs when the API changes.
Run the checks above before submitting. Use Conventional Commits for commit messages and PR titles.
Report vulnerabilities through [SECURITY.md](SECURITY.md).
Maintainers follow [RELEASING.md](RELEASING.md).
