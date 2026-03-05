## Document Prefix Renamer (GUI)

This repository includes a lightweight Windows GUI for the document prefix renamer:

- `doc_prefix_gui.pyw` (Tkinter GUI, no third-party dependencies)
- `doc_prefix.py` (shared core rename logic + CLI)

The GUI reuses the same planning/apply logic as the CLI and uses this default naming format:

`YYYYMM - Lastname, Firstname - <existing filename>`

### Features

- Preview-first workflow (safe by default)
- Recursive mode
- Force mode (re-prefix already-prefixed files)
- Conflict handling: `skip`, `suffix`, `overwrite`
- Editable prefix template in the GUI (default preserves the format above)
  - Supported placeholders: `{yyyymm}`, `{last}`, `{first}`
- Date modes:
  - Current month
  - File modified time (mtime)
  - Custom `YYYYMM`

### Safety Notes

- Recursive mode does not follow directory symlinks; symlinked directories are skipped in preview.
- On Windows, invalid destination basenames (reserved device names, trailing dot/space) are skipped with a clear reason.

## Windows: Create a Desktop Shortcut (No Need to Open the Script)

You can launch the GUI directly from a Desktop shortcut without opening the script file.

### Option 1 (Recommended): `pyw` launcher

Use the Windows Python GUI launcher (`pyw.exe`, per PEP 397). This avoids opening a console window.

Shortcut **Target** example:

```text
pyw -3 "C:\full\path\to\doc_prefix_gui.pyw"
```

### Option 2: Direct `pythonw.exe` path (does not require PATH)

If `pyw` is not available on your PATH, point the shortcut directly to `pythonw.exe`.

Shortcut **Target** example:

```text
"C:\Users\<you>\AppData\Local\Programs\Python\Python3x\pythonw.exe" "C:\full\path\to\doc_prefix_gui.pyw"
```

`pythonw.exe` (and `.pyw` files) run without opening a console window.

### How to Create the Shortcut

1. Right-click your Desktop and choose **New > Shortcut**.
2. Paste one of the **Target** commands above.
3. Name it something like `Document Prefix Renamer`.
4. (Optional) Right-click the shortcut > **Properties** > **Change Icon...** to assign a custom icon.

## GUI to CLI Mapping (Reference)

- Directory field -> positional `dir`
- First name / Last name -> `--first` / `--last`
- Recursive -> `--recursive`
- Force -> `--force`
- Conflict dropdown -> `--conflict skip|suffix|overwrite`
- Date mode:
  - Current month -> default behavior
  - Use file mtime -> `--use-mtime`
  - Custom YYYYMM -> `--date YYYYMM`
- Preview button -> dry-run preview (no `--apply`)
- Apply button -> executes renames (`--apply`) after confirmation
