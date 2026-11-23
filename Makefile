PYTHON := venv/Scripts/python.exe

.PHONY: install migrate users run pre-commit pre-commit-install

## Install dependencies into the venv
install:
	$(PYTHON) -m pip install -r requirements.txt

## Create the database tables
migrate:
	$(PYTHON) manage.py migrate

## Create the demo users alice and bob
users:
	$(PYTHON) manage.py create_demo_users

## Start the server at http://127.0.0.1:8000
run:
	$(PYTHON) -m uvicorn sample_project.asgi:application --reload

## Run all pre-commit hooks on every file
pre-commit:
	$(PYTHON) -m pre_commit run --all-files

## Install pre-commit into the venv and register the git hook
pre-commit-install:
	$(PYTHON) -m pip install pre-commit
	$(PYTHON) -m pre_commit install
