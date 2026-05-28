# Inventory Transaction Manager

Desktop inventory transaction tracker with transaction entry, aliases, overview tables, custom fields, CSV export, and project-directory persistence.

## Requirements

- Python 3.10+
- Dependencies from `requirements.txt`

## Install

```bash
python setup.py --venv
```

Or manually:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux or macOS, activate the virtual environment with `source .venv/bin/activate`.

## Run Desktop App

```bash
python inventory_transaction_manager.py
```

The app writes local runtime settings to `config.json` beside the script. Project data is stored in the selected project directory.

## Web Project

The `web/` folder is a Synticore web parity project. `package.json` contains wrapper scripts that expect a local compiler checkout at:

```text
tools/synticore-website-compiler
```

Run from this repository:

```bash
npm run inventory-manager:web:build
npm run inventory-manager:web:browser
```
