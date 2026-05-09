# Inventory Transaction Manager Web

This folder contains the Synticore project for the browser-based parity track of the Python Inventory Transaction Manager.

## Layout

- `inventory_transaction_manager/` is the npm root for this web surface.
- `inventory_transaction_manager/web/` contains the nested Synticore project so its build files do not mix with the Python app files.
- `inventory_transaction_manager/web/in/` is the editable project source.
- `inventory_transaction_manager/web/out/` is generated output.

## Commands

Run from `inventory_transaction_manager/`:

```bash
npm run inventory-manager:web:build
npm run inventory-manager:web:browser
```

The commands call the sibling `synticore-website-compiler` repository against this nested project path.
