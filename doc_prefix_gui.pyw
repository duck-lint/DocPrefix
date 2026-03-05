# Windows launch (no console):
# - `.pyw` files launched via `pyw.exe` / `pythonw.exe` do not open a console window.
# - Desktop shortcut target examples:
#   pyw -3 "C:\full\path\to\doc_prefix_gui.pyw"
#   "C:\...\pythonw.exe" "C:\full\path\to\doc_prefix_gui.pyw"
# - `pyw` is the GUI launcher from PEP 397. If you target `pythonw.exe` directly,
#   PATH is not required.

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from doc_prefix import (
    DEFAULT_PREFIX_TEMPLATE,
    PlanItem,
    __version__,
    apply_plan,
    parse_yyyymm_arg,
    plan_renames,
    rel_display,
    validate_prefix_template,
    yyyymm_from_now,
)


class DocPrefixGui(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.grid(sticky="nsew")

        self.directory_var = tk.StringVar()
        self.first_var = tk.StringVar()
        self.last_var = tk.StringVar()
        self.template_var = tk.StringVar(value=DEFAULT_PREFIX_TEMPLATE)
        self.recursive_var = tk.BooleanVar(value=False)
        self.force_var = tk.BooleanVar(value=False)
        self.conflict_var = tk.StringVar(value="suffix")
        self.date_mode_var = tk.StringVar(value="current")
        self.custom_date_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready. Fill in the fields, then click Preview.")

        self._last_preview_plan: list[PlanItem] | None = None
        self._last_preview_root: Path | None = None
        self._preview_valid = False

        self._build_ui()
        self._wire_events()
        self._toggle_custom_date_entry()
        self._set_apply_enabled(False)

    def _build_ui(self) -> None:
        self.master.title(f"Document Prefix Renamer v{__version__}")
        self.master.geometry("900x650")
        self.master.minsize(760, 520)
        self._build_menu()

        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        form = ttk.Frame(self)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Directory:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.directory_entry = ttk.Entry(form, textvariable=self.directory_var)
        self.directory_entry.grid(row=0, column=1, columnspan=3, sticky="ew")
        ttk.Button(form, text="Browse...", command=self.on_browse).grid(
            row=0, column=4, sticky="e", padx=(6, 0)
        )

        ttk.Label(form, text="First name:").grid(
            row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 6)
        )
        self.first_entry = ttk.Entry(form, textvariable=self.first_var)
        self.first_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(form, text="Last name:").grid(
            row=1, column=2, sticky="w", pady=(8, 0), padx=(12, 6)
        )
        self.last_entry = ttk.Entry(form, textvariable=self.last_var)
        self.last_entry.grid(row=1, column=3, sticky="ew", pady=(8, 0))

        ttk.Label(form, text="Template:").grid(
            row=2, column=0, sticky="w", pady=(8, 0), padx=(0, 6)
        )
        self.template_entry = ttk.Entry(form, textvariable=self.template_var)
        self.template_entry.grid(row=2, column=1, columnspan=4, sticky="ew", pady=(8, 0))

        options = ttk.Frame(form)
        options.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(10, 0))
        options.columnconfigure(5, weight=1)

        ttk.Checkbutton(options, text="Recursive", variable=self.recursive_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(options, text="Force", variable=self.force_var).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        ttk.Label(options, text="Conflict:").grid(row=0, column=2, sticky="w", padx=(16, 6))
        self.conflict_combo = ttk.Combobox(
            options,
            textvariable=self.conflict_var,
            values=("skip", "suffix", "overwrite"),
            state="readonly",
            width=12,
        )
        self.conflict_combo.grid(row=0, column=3, sticky="w")

        self.date_frame = ttk.LabelFrame(form, text="Date Mode")
        self.date_frame.grid(row=4, column=0, columnspan=5, sticky="ew", pady=(10, 0))
        self.date_frame.columnconfigure(3, weight=1)

        ttk.Radiobutton(
            self.date_frame,
            text="Current month",
            variable=self.date_mode_var,
            value="current",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6)

        ttk.Radiobutton(
            self.date_frame,
            text="Use file mtime",
            variable=self.date_mode_var,
            value="mtime",
        ).grid(row=0, column=1, sticky="w", padx=(8, 12), pady=6)

        ttk.Radiobutton(
            self.date_frame,
            text="Custom YYYYMM",
            variable=self.date_mode_var,
            value="custom",
        ).grid(row=0, column=2, sticky="w", padx=(8, 6), pady=6)

        self.custom_date_entry = ttk.Entry(
            self.date_frame, textvariable=self.custom_date_var, width=12
        )
        self.custom_date_entry.grid(row=0, column=3, sticky="w", padx=(0, 8), pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(10, 0))

        self.preview_button = ttk.Button(actions, text="Preview", command=self.on_preview)
        self.preview_button.grid(row=0, column=0, sticky="w")

        self.apply_button = ttk.Button(actions, text="Apply", command=self.on_apply)
        self.apply_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.clear_button = ttk.Button(
            actions, text="Clear Preview", command=self.on_clear_preview
        )
        self.clear_button.grid(row=0, column=2, sticky="w", padx=(8, 0))

        preview_frame = ttk.LabelFrame(self, text="Preview")
        preview_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.preview_text = tk.Text(
            preview_frame,
            wrap="none",
            height=20,
            state="disabled",
            font=("TkFixedFont", 10),
        )
        self.preview_text.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(
            preview_frame, orient="horizontal", command=self.preview_text.xview
        )
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.preview_text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.status_label = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(8, 0))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.master)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self.on_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.master.configure(menu=menubar)

    def _wire_events(self) -> None:
        for var in (
            self.directory_var,
            self.first_var,
            self.last_var,
            self.template_var,
            self.recursive_var,
            self.force_var,
            self.conflict_var,
            self.custom_date_var,
        ):
            var.trace_add("write", self._mark_preview_dirty)

        self.date_mode_var.trace_add("write", self._on_date_mode_changed)

        self.master.bind("<F5>", lambda event: self.on_preview())
        self.master.bind("<Control-Return>", lambda event: self.on_preview())

    def _on_date_mode_changed(self, *_args: object) -> None:
        self._toggle_custom_date_entry()
        self._mark_preview_dirty()

    def _toggle_custom_date_entry(self) -> None:
        if self.date_mode_var.get() == "custom":
            self.custom_date_entry.state(["!disabled"])
        else:
            self.custom_date_entry.state(["disabled"])

    def _set_apply_enabled(self, enabled: bool) -> None:
        if enabled:
            self.apply_button.state(["!disabled"])
        else:
            self.apply_button.state(["disabled"])

    def _mark_preview_dirty(self, *_args: object) -> None:
        self._preview_valid = False
        self._last_preview_plan = None
        self._last_preview_root = None
        self._set_apply_enabled(False)
        self.status_var.set("Inputs changed. Preview again before applying.")

    def _show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self.master)

    def on_about(self) -> None:
        messagebox.showinfo(
            "About DocPrefix",
            (
                f"DocPrefix v{__version__}\n\n"
                "Local document filename prefixing utility.\n"
                "Template field supports safe placeholders for date/name customization.\n"
                "Preview-first workflow with confirmation before applying renames.\n"
                "No network access is used by this tool."
            ),
            parent=self.master,
        )

    def _collect_form_inputs(self) -> dict[str, object]:
        directory_text = self.directory_var.get().strip()
        if not directory_text:
            raise ValueError("Directory is required.")

        root = Path(directory_text).expanduser()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Directory does not exist or is not a folder:\n{root}")

        first = self.first_var.get().strip()
        last = self.last_var.get().strip()
        template = self.template_var.get()
        if not first:
            raise ValueError("First name is required.")
        if not last:
            raise ValueError("Last name is required.")
        try:
            validate_prefix_template(template)
        except ValueError as exc:
            raise ValueError(f"Invalid template: {exc}") from exc

        conflict = self.conflict_var.get().strip()
        if conflict not in {"skip", "suffix", "overwrite"}:
            raise ValueError(f"Invalid conflict policy: {conflict}")

        date_mode = self.date_mode_var.get()
        if date_mode == "current":
            date_yyyymm = yyyymm_from_now()
            use_mtime = False
        elif date_mode == "mtime":
            date_yyyymm = None
            use_mtime = True
        elif date_mode == "custom":
            custom = self.custom_date_var.get().strip()
            if not custom:
                raise ValueError("Custom YYYYMM is required when custom date mode is selected.")
            try:
                date_yyyymm = parse_yyyymm_arg(custom)
            except argparse.ArgumentTypeError as exc:
                raise ValueError(str(exc)) from exc
            use_mtime = False
        else:
            raise ValueError(f"Invalid date mode: {date_mode}")

        return {
            "root": root,
            "first": first,
            "last": last,
            "template": template,
            "recursive": bool(self.recursive_var.get()),
            "force": bool(self.force_var.get()),
            "conflict": conflict,
            "date_yyyymm": date_yyyymm,
            "use_mtime": use_mtime,
        }

    def _compute_plan(self) -> tuple[Path, list[PlanItem]]:
        params = self._collect_form_inputs()
        root = params.pop("root")
        assert isinstance(root, Path)
        plan = plan_renames(root, **params)
        return root, plan

    def _format_preview(self, root: Path, plan: list[PlanItem]) -> str:
        renames = [it for it in plan if it.reason.startswith("rename")]
        skips = [it for it in plan if not it.reason.startswith("rename")]

        lines = [
            f"Directory: {root}",
            f"Planned renames: {len(renames)} | Skips: {len(skips)}",
            "",
        ]

        for it in plan:
            src_disp = rel_display(root, it.src)
            if it.reason.startswith("rename"):
                dst_disp = rel_display(root, it.dst)
                lines.append(f"RENAME: {src_disp}  ->  {dst_disp}")
            else:
                lines.append(f"{it.reason.upper()}: {src_disp}")

        if not plan:
            lines.append("(No files found.)")

        return "\n".join(lines)

    def _set_preview_text(self, text: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")
        self.preview_text.yview_moveto(0.0)
        self.preview_text.xview_moveto(0.0)

    def _confirm_apply(self, root: Path, plan: list[PlanItem]) -> bool:
        renames = sum(1 for it in plan if it.reason.startswith("rename"))
        skips = len(plan) - renames
        summary = (
            "Apply these renames?\n\n"
            f"Directory: {root}\n"
            f"Planned renames: {renames}\n"
            f"Skips: {skips}\n"
            f"Conflict policy: {self.conflict_var.get()}\n"
            f"Recursive: {'Yes' if self.recursive_var.get() else 'No'}\n"
            f"Force: {'Yes' if self.force_var.get() else 'No'}\n\n"
            "This will rename files on disk and is not automatically undoable."
        )
        return messagebox.askyesno(
            "Confirm Apply", summary, icon="warning", parent=self.master
        )

    def on_browse(self) -> None:
        current = self.directory_var.get().strip()
        initialdir = current if current else str(Path.home())
        selected = filedialog.askdirectory(
            parent=self.master, title="Choose directory", initialdir=initialdir
        )
        if selected:
            self.directory_var.set(selected)

    def on_clear_preview(self) -> None:
        self._set_preview_text("")
        self._preview_valid = False
        self._last_preview_plan = None
        self._last_preview_root = None
        self._set_apply_enabled(False)
        self.status_var.set("Preview cleared.")

    def on_preview(self) -> None:
        try:
            root, plan = self._compute_plan()
        except Exception as exc:
            self._show_error("Preview Error", str(exc))
            self._set_apply_enabled(False)
            self._preview_valid = False
            return

        self._set_preview_text(self._format_preview(root, plan))
        self._last_preview_root = root
        self._last_preview_plan = plan
        self._preview_valid = True
        self._set_apply_enabled(True)
        self.status_var.set("Preview generated successfully.")

    def on_apply(self) -> None:
        if not self._preview_valid:
            messagebox.showinfo(
                "Preview Required",
                "Please click Preview before applying renames.",
                parent=self.master,
            )
            return

        try:
            root, plan = self._compute_plan()
        except Exception as exc:
            self._show_error("Apply Error", str(exc))
            return

        self._set_preview_text(self._format_preview(root, plan))
        self._last_preview_root = root
        self._last_preview_plan = plan

        renames = [it for it in plan if it.reason.startswith("rename")]
        if not renames:
            self._preview_valid = True
            self._set_apply_enabled(True)
            self.status_var.set("Nothing to rename.")
            messagebox.showinfo(
                "Nothing to Rename",
                "There are no rename operations in the current plan.",
                parent=self.master,
            )
            return

        if not self._confirm_apply(root, plan):
            self.status_var.set("Apply canceled.")
            return

        try:
            renamed_count, skipped_count = apply_plan(plan, conflict=self.conflict_var.get())
        except Exception as exc:
            self._mark_preview_dirty()
            self._show_error(
                "Apply Error",
                f"{exc}\n\nSome files may already have been renamed before the error.",
            )
            return

        messagebox.showinfo(
            "Apply Complete",
            f"Done.\nRenamed: {renamed_count}\nSkipped: {skipped_count}",
            parent=self.master,
        )

        try:
            refreshed_root, refreshed_plan = self._compute_plan()
            self._set_preview_text(self._format_preview(refreshed_root, refreshed_plan))
            self._last_preview_root = refreshed_root
            self._last_preview_plan = refreshed_plan
            self._preview_valid = True
            self._set_apply_enabled(True)
            self.status_var.set("Apply complete. Preview refreshed.")
        except Exception as exc:
            self._mark_preview_dirty()
            self._show_error("Refresh Error", f"Renames completed, but refresh failed:\n{exc}")


def main() -> None:
    root = tk.Tk()
    app = DocPrefixGui(root)
    app.directory_entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
