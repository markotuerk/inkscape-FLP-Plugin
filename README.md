# Inkscape FLP-Plugin

This repository contains the project structure for an Inkscape extension plugin named "FLP Plugin".

## Project layout

- `src/flp_plugin/` – Python package for the plugin logic.
- `extensions/` – installable Inkscape extension entry points (`.py` + `.inx`).
- `tests/` – smoke tests for the package import and basic behavior.
- `docs/` – future documentation and examples.

## Quick start

1. Create a virtual environment.
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Run the smoke test:
   ```bash
   pytest
   ```
4. Copy the files from `extensions/` into your Inkscape extensions directory to test the plugin in Inkscape.

## Planned features

- Import/export of FLP-based assets
- Basic SVG processing
- Inkscape UI for plugin settings
- Automated validation tests

## Notes

This repository is intentionally scaffolded as a clean starting point. You can expand the plugin logic in `src/flp_plugin/` and the Inkscape extension wrapper in `extensions/`.
