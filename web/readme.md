# Inventory Transaction Manager Web

Synticore browser project for the web parity track of Inventory Transaction Manager.

## Layout

- `in/`: editable source
- `out/`: generated output, ignored by Git
- `config.json`: web project config
- `config.schema.json`: project-specific config schema
- `info.json`: project version metadata

## Build

Use the wrapper scripts from the repository root:

```bash
npm run inventory-manager:web:build
npm run inventory-manager:web:browser
```

Those scripts expect the Synticore compiler to be available at `tools/synticore-website-compiler` in the repository root.
