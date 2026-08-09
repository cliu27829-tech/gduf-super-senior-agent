from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.entities import User
from app.services.knowledge_service import (
    KnowledgeImportError,
    create_import_job,
    extract_document,
    finish_import_job,
    import_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import approved local documents into a user's private knowledge base.")
    parser.add_argument("source", type=Path, help="Explicitly approved source directory")
    parser.add_argument("--owner-email", default="", help="Existing owner account; omitted selects the first active admin/user")
    parser.add_argument("--extensions", nargs="+", default=[".md"], help="Allowed extensions for this run")
    parser.add_argument("--commit", action="store_true", help="Write imported documents; otherwise perform a read-only dry-run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        raise SystemExit("source must be an existing directory")
    extensions = {item.lower() if item.startswith(".") else f".{item.lower()}" for item in args.extensions}
    files = sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in extensions)
    total_bytes = sum(path.stat().st_size for path in files)
    if not args.commit:
        print(json.dumps({
            "mode": "dry-run",
            "source_name": source.name,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "extensions": sorted(extensions),
            "raw_files_will_be_copied": False,
        }, ensure_ascii=False))
        return 0

    settings = get_settings()
    errors: list[str] = []
    document_ids: list[str] = []
    with SessionLocal() as db:
        user_query = select(User).where(User.is_active.is_(True))
        if args.owner_email:
            user_query = user_query.where(User.email == args.owner_email.strip().lower())
        else:
            user_query = user_query.order_by((User.role == "admin").desc(), User.created_at)
        owner = db.scalar(user_query)
        if not owner:
            raise SystemExit("no eligible owner account exists; register or pass --owner-email")
        job = create_import_job(db, user_id=owner.id, source_label=source.name, total_files=len(files))
        for path in files:
            relative_name = path.relative_to(source).as_posix()
            try:
                if path.stat().st_size > settings.max_upload_bytes:
                    raise KnowledgeImportError("file exceeds configured size limit")
                content = extract_document(path.name, path.read_bytes())
                outcome = import_document(
                    db,
                    user_id=owner.id,
                    title=path.stem,
                    content=content,
                    source_type="local_file",
                    original_filename=path.name,
                    campus_id=owner.campus_id,
                )
                job.duplicate_files += int(outcome.duplicate)
                job.imported_files += int(not outcome.duplicate)
                if outcome.document:
                    document_ids.append(outcome.document.id)
            except (KnowledgeImportError, OSError) as exc:
                job.failed_files += 1
                errors.append(f"{relative_name}: {exc}")
        finish_import_job(job, errors=errors)
        db.commit()
        result = {
            "mode": "commit",
            "job_id": job.id,
            "source_name": source.name,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "imported": job.imported_files,
            "duplicates": job.duplicate_files,
            "failed": job.failed_files,
            "raw_files_copied": False,
            "errors": errors[:20],
        }

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_directory = settings.data_root / "import_logs"
    index_directory = settings.data_root / "private_indexes"
    import_directory = settings.data_root / "private_imports" / "haoren_shixiong"
    for directory in (log_directory, index_directory, import_directory):
        directory.mkdir(parents=True, exist_ok=True)
    (log_directory / f"knowledge-import-{timestamp}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (index_directory / "haoren-shixiong-manifest.json").write_text(
        json.dumps({
            "job_id": result["job_id"],
            "documents": len(document_ids),
            "source_name": source.name,
            "raw_files_copied": False,
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
