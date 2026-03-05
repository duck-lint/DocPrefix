#!/usr/bin/env python3
"""
doc_prefix.py

Prefix filenames with:
  YYYYMM - Lastname, Firstname - <existing filename>

Safe by default: prints planned renames. Use --apply to execute.
"""

from __future__ import annotations

import argparse
import os
import re
import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional
from uuid import uuid4

__version__ = "0.2.1"

# Matches: "202602 - Lastname, Firstname - "
PREFIX_RE = re.compile(r"^(?P<yyyymm>\d{6}) - (?P<last>.+?), (?P<first>.+?) - ")


WINDOWS_FORBIDDEN = r'<>:"/\|?*'
DEFAULT_PREFIX_TEMPLATE = "{yyyymm} - {last}, {first} - "
SUPPORTED_PREFIX_TEMPLATE_FIELDS = ("yyyymm", "last", "first")
SUPPORTED_PREFIX_PLACEHOLDERS = tuple(
    f"{{{name}}}" for name in SUPPORTED_PREFIX_TEMPLATE_FIELDS
)


def sanitize_component(s: str) -> str:
    s = s.strip()
    # Replace forbidden filename chars (esp. on Windows)
    trans = {ord(ch): "_" for ch in WINDOWS_FORBIDDEN}
    s = s.translate(trans)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def parse_yyyymm_arg(value: str) -> str:
    if not re.fullmatch(r"\d{6}", value):
        raise argparse.ArgumentTypeError("--date must be YYYYMM (e.g., 202602)")
    return value


def validate_prefix_template(template: str) -> None:
    supported = ", ".join(SUPPORTED_PREFIX_PLACEHOLDERS)
    if not template or not template.strip():
        raise ValueError(
            f"Template must not be empty. Supported placeholders: {supported}"
        )

    formatter = string.Formatter()
    unknown_fields: set[str] = set()
    try:
        for _literal, field_name, format_spec, conversion in formatter.parse(template):
            if field_name is None:
                continue
            if field_name == "":
                raise ValueError(
                    f"Template contains an empty placeholder. Supported placeholders: {supported}"
                )
            if conversion:
                raise ValueError(
                    f"Template conversions are not supported. Supported placeholders: {supported}"
                )
            if format_spec:
                raise ValueError(
                    f"Template format specifiers are not supported. Supported placeholders: {supported}"
                )
            if field_name not in SUPPORTED_PREFIX_TEMPLATE_FIELDS:
                unknown_fields.add(field_name)
    except ValueError as exc:
        raise ValueError(
            f"Invalid template syntax: {exc}. Supported placeholders: {supported}"
        ) from exc

    if unknown_fields:
        unknown_list = ", ".join(sorted(f"{{{name}}}" for name in unknown_fields))
        raise ValueError(
            f"Unsupported placeholder(s): {unknown_list}. Supported placeholders: {supported}"
        )


def yyyymm_from_now() -> str:
    # Uses local machine timezone settings
    return datetime.now().strftime("%Y%m")


def yyyymm_from_mtime(p: Path) -> str:
    ts = p.stat().st_mtime
    return datetime.fromtimestamp(ts).strftime("%Y%m")


@dataclass(frozen=True)
class PlanItem:
    src: Path
    dst: Path
    reason: str  # "rename" | "skip:..."


WINDOWS_RESERVED_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
}


def is_windows_reserved_name(name: str) -> bool:
    normalized = name.rstrip(" .")
    if not normalized:
        return False
    device_stem = normalized.split(".", 1)[0].casefold()
    return device_stem in WINDOWS_RESERVED_DEVICE_NAMES


def is_windows_bad_trailing(name: str) -> bool:
    return name.endswith(" ") or name.endswith(".")


def invalid_windows_destination_reason(name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    if is_windows_bad_trailing(name):
        return "trailing-dot-space"
    if is_windows_reserved_name(name):
        return "reserved-device-name"
    return None


def discover_files(
    root: Path, recursive: bool
) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    skipped_symlink_dirs: list[Path] = []

    if recursive:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            current = Path(dirpath)
            dirnames.sort()
            filenames.sort()

            kept_dirnames: list[str] = []
            for dirname in dirnames:
                dpath = current / dirname
                if dpath.is_symlink():
                    skipped_symlink_dirs.append(dpath)
                else:
                    kept_dirnames.append(dirname)
            dirnames[:] = kept_dirnames

            for filename in filenames:
                p = current / filename
                if p.is_file():
                    files.append(p)
    else:
        files = [p for p in root.iterdir() if p.is_file()]

    files.sort(key=lambda p: p.relative_to(root).as_posix())
    skipped_symlink_dirs.sort(key=lambda p: p.relative_to(root).as_posix())
    return files, skipped_symlink_dirs


def iter_files(root: Path, recursive: bool) -> Iterator[Path]:
    files, _skipped_symlink_dirs = discover_files(root, recursive)
    yield from files


def _path_key(p: Path) -> str:
    s = str(p)
    return s.casefold() if os.name == "nt" else s


def choose_nonconflicting_path(
    dst: Path, *, reserved_dst_keys: Optional[set[str]] = None
) -> Path:
    """
    If dst exists, return dst with " (n)" inserted before extension.
    Example: "file.pdf" -> "file (1).pdf"
    """
    if reserved_dst_keys is None:
        reserved_dst_keys = set()

    if not dst.exists() and _path_key(dst) not in reserved_dst_keys:
        return dst

    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent

    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if (
            not candidate.exists()
            and _path_key(candidate) not in reserved_dst_keys
        ):
            return candidate
        n += 1


def build_prefix(
    first: str,
    last: str,
    *,
    date_yyyymm: Optional[str],
    use_mtime: bool,
    file_path: Optional[Path],
    template: str = DEFAULT_PREFIX_TEMPLATE,
) -> str:
    first_s = sanitize_component(first)
    last_s = sanitize_component(last)

    if date_yyyymm is not None:
        yyyymm = date_yyyymm
    elif use_mtime:
        if file_path is None:
            raise ValueError("Internal error: file_path required for --use-mtime")
        yyyymm = yyyymm_from_mtime(file_path)
    else:
        raise ValueError(
            "Internal error: date_yyyymm must be provided when not using --use-mtime"
        )

    validate_prefix_template(template)
    return template.format(yyyymm=yyyymm, last=last_s, first=first_s)


def plan_renames(
    root: Path,
    *,
    first: str,
    last: str,
    recursive: bool,
    force: bool,
    conflict: str,
    date_yyyymm: Optional[str],
    use_mtime: bool,
    template: str = DEFAULT_PREFIX_TEMPLATE,
) -> list[PlanItem]:
    items: list[PlanItem] = []
    files, skipped_symlink_dirs = discover_files(root, recursive)

    for dpath in skipped_symlink_dirs:
        items.append(PlanItem(dpath, dpath, "skip:symlink-dir"))

    reserved_dst_keys: set[str] = set()
    first_s = sanitize_component(first)
    last_s = sanitize_component(last)
    desired_first = first_s.casefold()
    desired_last = last_s.casefold()
    validate_prefix_template(template)

    for p in files:
        name = p.name

        if date_yyyymm is not None:
            desired_yyyymm = date_yyyymm
        elif use_mtime:
            try:
                desired_yyyymm = yyyymm_from_mtime(p)
            except OSError:
                items.append(PlanItem(p, p, "skip:mtime-unavailable"))
                continue
        else:
            raise ValueError(
                "Internal error: date_yyyymm must be provided when not using --use-mtime"
            )

        prefix = template.format(
            yyyymm=desired_yyyymm,
            last=last_s,
            first=first_s,
        )

        if not force:
            existing_prefix = PREFIX_RE.match(name)
            if existing_prefix:
                existing_yyyymm = existing_prefix.group("yyyymm")
                existing_last = sanitize_component(existing_prefix.group("last")).casefold()
                existing_first = sanitize_component(existing_prefix.group("first")).casefold()
                if (
                    existing_yyyymm == desired_yyyymm
                    and existing_last == desired_last
                    and existing_first == desired_first
                ):
                    items.append(PlanItem(p, p, "skip:already-prefixed"))
                    continue

                remainder_name = name[existing_prefix.end() :]
                new_name = prefix + remainder_name
            else:
                new_name = prefix + name
        else:
            new_name = prefix + name

        dst = p.with_name(new_name)
        dst_key = _path_key(dst)

        bad_dst = invalid_windows_destination_reason(dst.name)
        if bad_dst is not None:
            items.append(PlanItem(p, p, f"skip:invalid-destination:{bad_dst}"))
            continue

        if dst == p:
            items.append(PlanItem(p, p, "skip:no-change"))
            continue

        dst_exists = dst.exists()
        dst_reserved = dst_key in reserved_dst_keys
        dst_taken = dst_exists or dst_reserved
        if dst_taken:
            if conflict == "skip":
                reason = "skip:conflict-exists" if dst_exists else "skip:conflict-planned"
                items.append(PlanItem(p, dst, reason))
                continue
            if conflict == "suffix":
                dst2 = choose_nonconflicting_path(
                    dst, reserved_dst_keys=reserved_dst_keys
                )
                items.append(PlanItem(p, dst2, "rename"))
                reserved_dst_keys.add(_path_key(dst2))
                continue
            if conflict == "overwrite":
                if dst_reserved:
                    raise ValueError(
                        "Multiple sources target the same destination path in one plan; "
                        "use conflict='suffix' or conflict='skip'."
                    )
                items.append(PlanItem(p, dst, "rename:overwrite"))
                reserved_dst_keys.add(dst_key)
                continue

        items.append(PlanItem(p, dst, "rename"))
        reserved_dst_keys.add(dst_key)

    return items


def rel_display(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def choose_temp_stage_path(
    src: Path,
    *,
    reserved_paths: set[Path],
) -> Path:
    parent = src.parent
    base_name = src.name
    while True:
        candidate = parent / f".{base_name}.doc_prefix_tmp_{uuid4().hex}"
        if candidate in reserved_paths:
            continue
        if not candidate.exists():
            return candidate


def _validate_overwrite_moves(moves: list[tuple[Path, Path]]) -> None:
    seen_src: set[Path] = set()
    seen_dst: set[Path] = set()

    for src, dst in moves:
        if src in seen_src:
            raise RuntimeError(f"Duplicate source path in rename plan: {src}")
        seen_src.add(src)

        if dst in seen_dst:
            raise RuntimeError(f"Duplicate destination path in rename plan: {dst}")
        seen_dst.add(dst)


def apply_overwrite_renames(plan: list[PlanItem]) -> int:
    moves = [(it.src, it.dst) for it in plan if it.reason.startswith("rename")]
    if not moves:
        return 0

    _validate_overwrite_moves(moves)

    pending: dict[Path, Path] = {src: dst for src, dst in moves}
    renamed = 0

    while pending:
        pending_sources = set(pending.keys())
        progressed = False

        for src, dst in list(pending.items()):
            if dst in pending_sources:
                continue

            try:
                os.replace(src, dst)
            except OSError as exc:
                raise RuntimeError(
                    f"Failed during overwrite replace: {src} -> {dst}: {exc}"
                ) from exc

            del pending[src]
            renamed += 1
            progressed = True

        if progressed:
            continue

        src, dst = next(iter(pending.items()))
        reserved = set(pending.keys()) | set(pending.values())
        temp = choose_temp_stage_path(src, reserved_paths=reserved)

        try:
            os.replace(src, temp)
        except OSError as exc:
            raise RuntimeError(
                f"Failed during overwrite cycle staging (stage-temp): "
                f"{src} -> {temp} (final {dst}): {exc}"
            ) from exc

        del pending[src]
        pending[temp] = dst

    return renamed


def apply_plan(plan: Iterable[PlanItem], *, conflict: str) -> tuple[int, int]:
    plan_list = list(plan)
    rename_items = [it for it in plan_list if it.reason.startswith("rename")]
    skipped = len(plan_list) - len(rename_items)

    if conflict == "overwrite":
        renamed = apply_overwrite_renames(rename_items)
        return renamed, skipped

    renamed = 0

    for it in rename_items:
        src = it.src
        dst = it.dst

        try:
            os.rename(src, dst)
        except OSError as exc:
            raise RuntimeError(f"Failed rename: {src} -> {dst}: {exc}") from exc
        renamed += 1

    return renamed, skipped


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prefix filenames with 'YYYYMM - Lastname, Firstname - '"
    )
    ap.add_argument("dir", type=Path, help="Directory containing files to rename")
    ap.add_argument("--first", required=True, help="First name")
    ap.add_argument("--last", required=True, help="Last name")

    ap.add_argument(
        "--recursive",
        action="store_true",
        help="Include files in subfolders (symlinked directories are skipped)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Rename even if file already looks prefixed",
    )
    ap.add_argument(
        "--date",
        type=parse_yyyymm_arg,
        default=None,
        help="Override date as YYYYMM (e.g., 202602). If omitted, uses current month.",
    )
    ap.add_argument(
        "--use-mtime",
        action="store_true",
        help="Use each file's modified time for YYYYMM instead of current month",
    )
    ap.add_argument(
        "--conflict",
        choices=["skip", "suffix", "overwrite"],
        default="suffix",
        help="What to do if target filename already exists",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files. Without this flag, only prints a preview.",
    )

    args = ap.parse_args()

    root = args.dir
    if not root.exists() or not root.is_dir():
        ap.error(f"Not a directory: {root}")

    if args.date is not None and args.use_mtime:
        ap.error("Use either --date or --use-mtime, not both.")

    if args.date is not None:
        run_date_yyyymm = args.date
    elif args.use_mtime:
        run_date_yyyymm = None
    else:
        run_date_yyyymm = yyyymm_from_now()

    plan = plan_renames(
        root,
        first=args.first,
        last=args.last,
        recursive=args.recursive,
        force=args.force,
        conflict=args.conflict,
        date_yyyymm=run_date_yyyymm,
        use_mtime=args.use_mtime,
    )

    # Print preview
    renames = [it for it in plan if it.reason.startswith("rename")]
    skips = [it for it in plan if not it.reason.startswith("rename")]

    print(f"\nDirectory: {root}")
    print(f"Planned renames: {len(renames)} | Skips: {len(skips)}\n")

    for it in plan:
        src_disp = rel_display(root, it.src)
        if it.reason.startswith("rename"):
            dst_disp = rel_display(root, it.dst)
            print(f"RENAME: {src_disp}  ->  {dst_disp}")
        else:
            print(f"{it.reason.upper()}: {src_disp}")

    if not args.apply:
        print("\nPreview only. Re-run with --apply to perform these renames.")
        return 0

    renamed, skipped = apply_plan(plan, conflict=args.conflict)
    print(f"\nDone. Renamed: {renamed} | Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
