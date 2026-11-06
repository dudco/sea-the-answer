"""Export, inspect and install a bounded navigation snapshot without network or DB access."""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from backend.tools.navigation_references import NavigationCatalog, Source, catalog_summary
from scripts.prepare_navigation_references import atomic_write, dump

LIMIT = 8 * 1024 * 1024


class BundleError(ValueError):
    """Safe operator message; never includes raw source content or configuration."""


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["HAEDAP-NAVIGATION-BUNDLE-1.0"]
    catalog_file: Literal["catalog.json"]
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_bytes: int = Field(gt=0, le=LIMIT)
    catalog_version: Literal["NAVIGATION-REFERENCES-1.0", "NAVIGATION-REFERENCES-1.1", "NAVIGATION-REFERENCES-1.2", "NAVIGATION-REFERENCES-1.3", "NAVIGATION-REFERENCES-1.4"]
    packed_at: AwareDatetime
    sources: list[Source] = Field(min_length=3, max_length=12)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, maximum=LIMIT):
    if path.is_symlink() or not path.is_file():
        raise BundleError("A regular, non-symlink file is required.")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if not data or len(data) > maximum:
        raise BundleError("File is empty or exceeds the size budget.")
    return data


def read_catalog(path):
    data = read_bounded(path)
    try:
        catalog = NavigationCatalog.model_validate_json(data)
    except (ValueError, ValidationError):
        raise BundleError("Catalog schema, identity or source references are invalid.") from None
    return data, catalog


def export_bundle(catalog_path, directory):
    data, catalog = read_catalog(catalog_path)
    manifest = Manifest(format="HAEDAP-NAVIGATION-BUNDLE-1.0", catalog_file="catalog.json",
        catalog_sha256=sha(data), catalog_bytes=len(data), catalog_version=catalog.version,
        packed_at=datetime.now(timezone.utc), sources=catalog.sources)
    # New directory only. A pre-existing export or unrelated files are never replaced.
    directory.mkdir(parents=True, exist_ok=False)
    atomic_write(directory / "catalog.json", data)
    lines = ["SEA THE ANSWER navigation reference bundle", "",
        "Reference comparison only; no entry permission or verified present draught.",
        "Packed time is not a new observation, survey or source effective date.",
        "No app accounts, .env, database dump or annual MRV rows are included.",
        "Original source captures must be archived separately.",
        "Hash checks detect changed bytes; trust in the publisher/transfer path is separate.", ""]
    for source in catalog.sources:
        lines.extend([source.attribution, str(source.url),
            "Captured: " + source.retrieved_at.isoformat(),
            "Original SHA256: " + source.sha256,
            "License: " + (str(source.license_url) if source.license_url else "No open license asserted; retain source terms"), ""])
    for doc in catalog.port_guidance:
        lines.extend([doc.attribution+' / '+doc.title, str(doc.url),
            'Captured: '+doc.retrieved_at.isoformat(), 'Original SHA256: '+doc.raw_sha256,
            'Main-text SHA256: '+doc.content_sha256, 'Displayed revision: '+str(doc.displayed_updated_on),
            'Effective date: '+str(doc.effective_on), 'No open license asserted; retain source terms', ''])
    atomic_write(directory / "SOURCES.txt", "\n".join(lines).encode("utf-8"))
    dump(directory / "manifest.json", manifest.model_dump(mode="json"))
    return inspect_bundle(directory)


def checked_bundle(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise BundleError("Bundle must be a regular directory.")
    # Fixed names only: the manifest cannot redirect reads to another path.
    try:
        manifest = Manifest.model_validate_json(read_bounded(directory / "manifest.json", 64 * 1024))
    except (ValueError, ValidationError):
        raise BundleError("Bundle manifest is invalid.") from None
    data, catalog = read_catalog(directory / "catalog.json")
    if len(data) != manifest.catalog_bytes or sha(data) != manifest.catalog_sha256:
        raise BundleError("Catalog hash/size differs from its manifest; no installation performed.")
    if catalog.version != manifest.catalog_version or (
        [s.model_dump(mode="json") for s in catalog.sources] != [s.model_dump(mode="json") for s in manifest.sources]
    ):
        raise BundleError("Bundle source/version metadata differs from the catalog.")
    return data, catalog, manifest


def inspection(catalog, digest):
    summary = catalog_summary(catalog, digest)
    return {"status": "checked", "catalog_sha256": digest, "version": catalog.version,
        "reference_only": True, "admission": "not_assessed", "generated_at": summary["generated_at"],
        "freshness": summary["freshness"], "ports": summary["ports"],
        "ais_observation_count": summary["ais_observation_count"],
        "official_guidance_documents":summary['official_guidance_documents'],
        "guidance_review_sha256":catalog.guidance_review_sha256,
        "notice": "Inspection uses the current clock. Installing does not renew source timestamps."}


def inspect_bundle(directory):
    data, catalog, _manifest = checked_bundle(directory)
    return inspection(catalog, sha(data))


@contextmanager
def installation_lock(target):
    lock = target.with_name("." + target.name + ".install.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise BundleError("Another install or a retained install lock exists; inspect it before retrying.") from None
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink()


def install_bundle(directory, target, *, expected_current_sha256=None):
    data, catalog, _manifest = checked_bundle(directory)
    if expected_current_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_current_sha256):
        raise BundleError("Expected current SHA256 must contain 64 lowercase hex characters.")
    if target.is_symlink():
        raise BundleError("Installation target must not be a symlink.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with installation_lock(target):
        old = read_bounded(target) if target.exists() else None
        if old is not None and (expected_current_sha256 is None or sha(old) != expected_current_sha256):
            raise BundleError("Existing target hash must match --expected-current-sha256; target was preserved.")
        if old is None and expected_current_sha256 is not None:
            raise BundleError("Expected target is missing; installation was not performed.")
        backup = None
        if old == data:
            return {**inspection(catalog, sha(data)), "status": "unchanged", "backup": None}
        if old is not None:
            backup = target.with_name(target.name + ".previous." + sha(old) + ".json")
            if backup.exists() or backup.is_symlink():
                if read_bounded(backup) != old:
                    raise BundleError("Existing backup conflicts with the previous target; target was preserved.")
            else:
                descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, stat.S_IMODE(target.stat().st_mode))
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(old)
                    stream.flush()
                    os.fsync(stream.fileno())
        # Cooperating installers are serialized; external target edits are also rechecked.
        if target.is_symlink() or (read_bounded(target) if target.exists() else None) != old:
            raise BundleError("Target changed during installation; no replacement performed.")
        atomic_write(target, data)
    return {**inspection(catalog, sha(data)), "status": "installed", "backup": backup.name if backup else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--catalog", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--bundle", type=Path, required=True)
    install = sub.add_parser("install")
    install.add_argument("--bundle", type=Path, required=True)
    install.add_argument("--target", type=Path, required=True)
    install.add_argument("--expected-current-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export_bundle(args.catalog, args.output)
        elif args.command == "inspect":
            result = inspect_bundle(args.bundle)
        else:
            result = install_bundle(args.bundle, args.target, expected_current_sha256=args.expected_current_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except BundleError as exc:
        print(str(exc))
        return 1
    except (OSError, ValueError):
        # No driver, raw-data or arbitrary file-content details in console errors.
        print("Bundle operation failed. Check files, source schema, SHA256, permissions and install lock.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
