# Document Prefix Renamer (DocPrefix)

A lightweight Windows tool for bulk-renaming files by applying or updating a filename prefix.

Default prefix format:
`YYYYMM - Lastname, Firstname - <existing filename remainder>`

Repo contents:
- `doc_prefix_gui.pyw` — Tkinter GUI (no third-party dependencies)
- `doc_prefix.py` — shared core rename logic + CLI

## What it does

- Preview-first workflow (nothing changes until Apply)
- Recursive mode (includes subfolders)
- Force mode (re-prefix already-prefixed files)
- Conflict handling: skip / suffix / overwrite
- Editable prefix template in the GUI  
  Supported placeholders: `{yyyymm}`, `{last}`, `{first}`
- Date modes:
  - Current month
  - File modified time (mtime)
  - Custom YYYYMM

## Quick start (recommended)

### Use the packaged Windows x64 executable from GitHub Releases.

Workflow:
1) Select a folder  
2) Set First/Last and date mode  
3) Click Preview  
4) Click Apply (after confirmation)

## Run from source (developer / verification)

Requires Python 3.x (Tkinter included with standard Python on Windows).

CLI help:
- `python doc_prefix.py --help`

Run tests:
- `python -m unittest -v`

Packaging smoke test:
- `python packaging/smoke_test.py`

## Safety and constraints

- Preview-first: no changes occur until Apply is pressed.
- Recursive mode does not follow directory symlinks. Symlinked directories are skipped in preview with `skip:symlink-dir`.  
  (This prevents accidental traversal outside the selected folder boundary.)
- On Windows, invalid destination basenames are skipped at plan time with a clear reason:
  - reserved device names: `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` (including forms like `CON.txt`)
  - basenames ending in a dot or space  
  These appear as `skip:invalid-destination:<detail>`.

## Preview reason codes (examples)

Preview output includes explicit skip reasons, such as:
- `skip:already-prefixed`
- `skip:conflict-planned`
- `skip:mtime-unavailable`
- `skip:symlink-dir`
- `skip:invalid-destination:<detail>`

## GUI to CLI mapping (reference)

- Directory field → positional `dir`
- First name / Last name → `--first` / `--last`
- Recursive → `--recursive`
- Force → `--force`
- Conflict dropdown → `--conflict skip|suffix|overwrite`
- Date mode:
  - Current month → default behavior
  - Use file mtime → `--use-mtime`
  - Custom YYYYMM → `--date YYYYMM`
- Preview button → dry-run preview (no `--apply`)
- Apply button → executes renames (`--apply`) after confirmation

## Windows: Desktop shortcut (source-only)

If you are running the GUI from source (not using the packaged exe), you can launch it via a shortcut without opening a console.

Option 1 (recommended): `pyw` launcher (PEP 397)
- Target example:
  - `pyw -3 "C:\full\path\to\doc_prefix_gui.pyw"`

Option 2: direct `pythonw.exe` path
- Target example:
  - `"C:\Users\<you>\AppData\Local\Programs\Python\Python3x\pythonw.exe" "C:\full\path\to\doc_prefix_gui.pyw"`
