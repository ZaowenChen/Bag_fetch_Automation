# BagFetcher

BagFetcher is a macOS-first GUI + CLI utility that stages and downloads robot bag files from remote hosts over SSH. The app targets Python 3.11+, PySide6, Paramiko, and macOS Keychain for password storage.

## Project layout
```
bagfetcher/
  app.py                # Qt bootstrap
  core/                 # Parser, models, SSH orchestration
  ui/                   # Qt widgets (connect panel, bag browser, downloads)
  packaging/            # Info.plist + entitlements for PyInstaller bundle
  resources/            # Placeholder Qt resource collection
  tests/                # Unit tests (pytest-style)
tools/
  cli_fetch.py          # CLI helper sharing the same core logic
pyproject.toml          # Project metadata + dependencies
```

## Quick start
1. Create/activate the supplied Conda env (or roll your own virtualenv):
   ```bash
   conda create -n BagFetch python=3.11
   conda activate BagFetch
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch the GUI:
   ```bash
   python -m bagfetcher.app
   ```
4. (Optional) Use the CLI helper for automation/tests:
   ```bash
   python -m tools.cli_fetch \
     --host ngrok-us0.gs-robot.com --port 45507 --user gaussian \
     --password '••••••' \
     --local-dir ~/RobotBags/siteA/2025-11-06 \
     --from '2025-11-06 09:10' --to '2025-11-06 09:15' \
     --cleanup
   ```
   Always provide a narrow `--from/--to` window so you do not pull hundreds of bags at once.

## Tests
The initial test suite focuses on the SSH paste parser:
```bash
conda run -n BagFetch pytest bagfetcher/tests/test_parser.py
```
(Install `pytest` if it is not already available: `pip install pytest`.)

## Packaging & signing
1. Build with PyInstaller:
   ```bash
   pyinstaller bagfetcher.spec
   ```
2. Codesign the resulting `dist/BagFetcher.app` bundle with `codesign --options runtime`.
3. Notarize via `xcrun notarytool submit … --wait`, then staple the ticket.

## Roadmap
- Add cancellation + retry controls to the download worker threads (currently single threaded, no cancel button).
- Surface `profiles.yaml` management UI plus Keychain toggles.
- Optional hash verification and remote cleanup prompts.
- Parallel downloads with bandwidth capping and richer filtering (last N files, etc.).
