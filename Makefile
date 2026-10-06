# Insurance Claims Analytics — one-command workflow.
# Assumes a local MySQL server is running and .env is filled in (see .env.example).

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help setup db load queries analyze model notebook all clean

help:
	@echo "make setup     - create .venv and install requirements"
	@echo "make db        - create the database + app user (prompts for MySQL root)"
	@echo "make load      - clean, normalize and load the CSV into MySQL"
	@echo "make queries   - run the 10 analytical SQL queries"
	@echo "make analyze   - execute the analysis notebook (regenerates charts/)"
	@echo "make model     - train the fraud-scoring model"
	@echo "make all       - load + queries + analyze + model"
	@echo "make clean     - remove derived CSVs, __pycache__, executed notebook outputs"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

db:
	@read -p "MySQL root password (blank if none): " ROOTPW; \
	read -p "Password to set for insurance_app user: " APPPW; \
	mysql -u root $${ROOTPW:+-p$$ROOTPW} -e "\
	  CREATE DATABASE IF NOT EXISTS insurance_claims CHARACTER SET utf8mb4; \
	  CREATE USER IF NOT EXISTS 'insurance_app'@'localhost' IDENTIFIED BY '$$APPPW'; \
	  GRANT ALL PRIVILEGES ON insurance_claims.* TO 'insurance_app'@'localhost'; \
	  FLUSH PRIVILEGES;"
	@echo "Now copy .env.example to .env and set DB_PASSWORD to the value you just chose."

load:
	$(PY) data/normalize_data.py

queries:
	$(PY) queries/run_queries.py

analyze:
	.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
	  analysis/analysis.ipynb --ExecutePreprocessor.timeout=180

model:
	$(PY) analysis/fraud_model.py

all: load queries analyze model

clean:
	rm -f data/policies.csv data/vehicles.csv data/incidents.csv data/claims.csv
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	.venv/bin/jupyter nbconvert --clear-output --inplace analysis/analysis.ipynb
