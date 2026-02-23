#!/usr/bin/env python3
"""Bulk-extract ZIP archives with duplicate-skip and path-safety protections.

Examples:
  python extract_zips.py --in_dir "C:\\MusicZips" --out_dir "C:\\Extracted" --subfolders
  python extract_zips.py --in_dir "C:\\MusicZips" --out_dir "C:\\AllMusic" --flat
  python extract_zips.py --in_dir ./zips --out_dir ./out --flat --dry_run --verbose
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable
import zipfile


@dataclass
class Summary:
    zips_found: int = 0
    zips_processed: int = 0
    bad_zips_skipped: int = 0
    files_extracted: int = 0
    files_skipped_duplicates: int = 0
    files_skipped_unsafe: int = 0
    other_errors_count: int = 0


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Examples:\n"
        '  python extract_zips.py --in_dir "C:\\MusicZips" --out_dir "C:\\Extracted" --subfolders\n'
        '  python extract_zips.py --in_dir "C:\\MusicZips" --out_dir "C:\\AllMusic" --flat\n'
        "  python extract_zips.py --in_dir ./zips --out_dir ./out --flat --dry_run --verbose\n"
    )
    parser = argparse.ArgumentParser(
        description="Bulk-extract ZIP files safely, skipping duplicates by default.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--in_dir", required=True, type=Path, help="directory containing .zip files")
    parser.add_argument("--out_dir", required=True, type=Path, help="directory to extract into")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--subfolders",
        action="store_true",
        help="extract each zip into a folder named after the zip stem",
    )
    mode_group.add_argument(
        "--flat",
        action="store_true",
        help="extract all contents directly into --out_dir (default if neither flag is given)",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing files instead of skipping duplicates",
    )
    parser.add_argument("--dry_run", action="store_true", help="print actions without writing files")
    parser.add_argument("--verbose", action="store_true", help="print per-file actions")
    return parser


def is_windows() -> bool:
    return os.name == "nt"


def dedupe_key(path: Path) -> str:
    text = str(path)
    return os.path.normcase(text) if is_windows() else text


def sanitize_member_relative_path(member_name: str) -> Path | None:
    """Return a safe relative path for a zip member, or None if unsafe."""
    # Reject Windows drive-prefixed paths (e.g., C:\foo or C:/foo).
    if PureWindowsPath(member_name).drive:
        return None

    # ZIP paths use forward slashes, but malformed archives may include backslashes.
    normalized = member_name.replace("\\", "/").lstrip("/")
    if not normalized:
        return None

    parts = []
    for part in PurePosixPath(normalized).parts:
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)

    if not parts:
        return None

    return Path(*parts)


def safe_destination_path(base_dir: Path, member_name: str) -> Path | None:
    rel_path = sanitize_member_relative_path(member_name)
    if rel_path is None:
        return None

    candidate = (base_dir / rel_path).resolve(strict=False)
    base_resolved = base_dir.resolve(strict=False)
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate


def ensure_dir(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    path.mkdir(parents=True, exist_ok=True)


def iter_zip_files(in_dir: Path) -> Iterable[Path]:
    return sorted((p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() == ".zip"), key=lambda p: p.name.lower())


def log(verbose: bool, message: str) -> None:
    if verbose:
        print(message)


def extract_member(
    zf: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    dest_file: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    ensure_dir(dest_file.parent, dry_run=False)
    with zf.open(member, "r") as src, open(dest_file, "wb") as dst:
        shutil.copyfileobj(src, dst)


def process_zip(
    zip_path: Path,
    zip_out_dir: Path,
    *,
    overwrite: bool,
    dry_run: bool,
    verbose: bool,
    reserved_output_paths: set[str],
    summary: Summary,
) -> None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.infolist()
            print(f"==> {zip_path.name} -> {zip_out_dir} ({len(members)} members)")
            summary.zips_processed += 1

            if not dry_run:
                zip_out_dir.mkdir(parents=True, exist_ok=True)

            for member in members:
                try:
                    dest_path = safe_destination_path(zip_out_dir, member.filename)
                    if dest_path is None:
                        summary.files_skipped_unsafe += 1
                        log(verbose, f"  [skip-unsafe] {member.filename!r}")
                        continue

                    is_dir_entry = member.is_dir() or member.filename.endswith(("/", "\\"))
                    if is_dir_entry:
                        if not dry_run:
                            dest_path.mkdir(parents=True, exist_ok=True)
                        log(verbose, f"  [dir] {member.filename!r} -> {dest_path}")
                        continue

                    key = dedupe_key(dest_path)
                    exists_collision = dest_path.exists()
                    reserved_collision = key in reserved_output_paths
                    if not overwrite and (exists_collision or reserved_collision):
                        summary.files_skipped_duplicates += 1
                        reason = "exists" if exists_collision else "run-collision"
                        log(verbose, f"  [skip-duplicate:{reason}] {member.filename!r} -> {dest_path}")
                        continue

                    extract_member(zf, member, dest_path, dry_run=dry_run)
                    summary.files_extracted += 1
                    log(verbose, f"  [extracted] {member.filename!r} -> {dest_path}")

                    # Reserve after successful extraction (or planned extraction in dry-run).
                    reserved_output_paths.add(key)
                except Exception as exc:  # noqa: BLE001 - continue processing other members
                    summary.other_errors_count += 1
                    log(verbose, f"  [error] {member.filename!r}: {exc}")
                    continue
    except zipfile.BadZipFile:
        summary.bad_zips_skipped += 1
        print(f"!! Skipping invalid zip: {zip_path}")
    except Exception as exc:  # noqa: BLE001 - continue processing remaining zips
        summary.other_errors_count += 1
        print(f"!! Error opening {zip_path}: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    in_dir = args.in_dir.expanduser()
    out_dir = args.out_dir.expanduser()
    flat_mode = not args.subfolders

    if not in_dir.exists():
        parser.error(f"--in_dir does not exist: {in_dir}")
    if not in_dir.is_dir():
        parser.error(f"--in_dir is not a directory: {in_dir}")

    summary = Summary()
    reserved_output_paths: set[str] = set()

    try:
        zip_files = list(iter_zip_files(in_dir))
    except Exception as exc:  # noqa: BLE001
        print(f"Error listing zip files in {in_dir}: {exc}", file=sys.stderr)
        return 2

    summary.zips_found = len(zip_files)

    if not args.dry_run:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Error creating output directory {out_dir}: {exc}", file=sys.stderr)
            return 2

    if summary.zips_found == 0:
        print(f"No .zip files found in {in_dir}")

    for zip_path in zip_files:
        zip_dest = out_dir / zip_path.stem if not flat_mode else out_dir
        process_zip(
            zip_path,
            zip_dest,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            verbose=args.verbose,
            reserved_output_paths=reserved_output_paths,
            summary=summary,
        )

    print("\nSummary:")
    print(f"  zips_found: {summary.zips_found}")
    print(f"  zips_processed: {summary.zips_processed}")
    print(f"  bad_zips_skipped: {summary.bad_zips_skipped}")
    print(f"  files_extracted: {summary.files_extracted}")
    print(f"  files_skipped_duplicates: {summary.files_skipped_duplicates}")
    print(f"  files_skipped_unsafe: {summary.files_skipped_unsafe}")
    print(f"  other_errors_count: {summary.other_errors_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
