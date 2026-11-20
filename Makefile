PRE_COMMIT := venv/bin/pre-commit

.PHONY: pre-commit pre-commit-install

## Run all pre-commit hooks (formatting, linting, checks) on every file
pre-commit:
	$(PRE_COMMIT) run --all-files

## Install pre-commit into the venv and register the git hook
pre-commit-install:
	venv/bin/pip install pre-commit
	$(PRE_COMMIT) install

.PHONY: test

## Run the test suite
test:
	venv/bin/python -m django test tests --settings=tests.settings
