#!/usr/bin/env python3
"""
Sample complaints reproducibly, export associated action histories,
and download related documents from S3.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from app.config import directories, settings


SQLITE_URL_PREFIX = "sqlite+aiosqlite:///"


@dataclass
class DownloadResult:
    ticket_no: str
    s3_key: Optional[str]
    local_path: Optional[str]
    status: str
    error: Optional[str]


def sqlite_path_from_db_url(db_url: str) -> Path:
    if db_url.startswith(SQLITE_URL_PREFIX):
        return Path(db_url[len(SQLITE_URL_PREFIX) :])
    raise ValueError(f"Unsupported DB_URL for this script: {db_url}")


def chunked(seq: Sequence[str], size: int) -> Iterator[List[str]]:
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def reservoir_sample(items: Iterable[str], k: int, seed: int) -> List[str]:
    rng = Random(seed)
    sample: List[str] = []
    n = 0
    for item in items:
        n += 1
        if len(sample) < k:
            sample.append(item)
        else:
            j = rng.randint(1, n)
            if j <= k:
                sample[j - 1] = item
    return sample


def iter_ticket_nos(conn: sqlite3.Connection) -> Iterator[str]:
    cursor = conn.execute("SELECT ticket_no FROM complaints ORDER BY ticket_no")
    for (ticket_no,) in cursor:
        if ticket_no is not None:
            yield str(ticket_no)


def export_rows_to_parquet(
    conn: sqlite3.Connection,
    table: str,
    ticket_nos: Sequence[str],
    output_path: Path,
    chunk_size: int = 900,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    writer = None
    schema = None
    for chunk in chunked(ticket_nos, chunk_size):
        placeholders = ",".join(["?"] * len(chunk))
        query = f"SELECT * FROM {table} WHERE ticket_no IN ({placeholders})"
        cursor = conn.execute(query, chunk)
        rows = cursor.fetchall()
        if not rows:
            continue
        columns = [col[0] for col in cursor.description]
        data = {col: [row[idx] for row in rows] for idx, col in enumerate(columns)}
        table_data = pa.Table.from_pydict(data)
        if schema is None:
            # Force nullable fields; promote null-only columns to string.
            fields = []
            for field in table_data.schema:
                field_type = field.type
                if pa.types.is_null(field_type):
                    field_type = pa.string()
                fields.append(pa.field(field.name, field_type, nullable=True))
            schema = pa.schema(fields)
        table_data = table_data.cast(schema, safe=False)
        if writer is None:
            writer = pq.ParquetWriter(str(output_path), schema)
        writer.write_table(table_data)
        total_rows += len(rows)
    if writer is not None:
        writer.close()
    return total_rows


def resolve_s3_key_by_prefix(
    ticket_no: str,
    s3_client,
    bucket: str,
    prefix_base: str = "",
) -> Optional[str]:
    prefix = f"{prefix_base}{ticket_no}_"
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    contents = response.get("Contents", [])
    if contents:
        return contents[0]["Key"]
    return None


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def download_one(
    ticket_no: str,
    s3_key: Optional[str],
    output_dir: Path,
    s3_client,
    bucket: str,
    overwrite: bool,
    restore_days: int,
    restore_tier: str,
) -> DownloadResult:
    if not s3_key:
        return DownloadResult(ticket_no, None, None, "missing_key", None)
    filename = safe_filename(Path(s3_key).name)
    local_path = output_dir / filename
    if local_path.exists() and not overwrite:
        return DownloadResult(ticket_no, s3_key, str(local_path), "exists", None)
    try:
        # Check storage class and restore if needed.
        head = s3_client.head_object(Bucket=bucket, Key=s3_key)
        storage_class = head.get("StorageClass")
        restore_header = head.get("Restore")
        cold_classes = {"GLACIER", "DEEP_ARCHIVE", "GLACIER_IR", "INTELLIGENT_TIERING"}
        if storage_class in cold_classes:
            if restore_header:
                if 'ongoing-request="true"' in restore_header:
                    return DownloadResult(
                        ticket_no,
                        s3_key,
                        str(local_path),
                        "restore_in_progress",
                        None,
                    )
                if 'ongoing-request="false"' in restore_header:
                    # Restored copy is available; proceed to download.
                    pass
                else:
                    # Unrecognized restore header format; fall through to request restore.
                    pass
            if not restore_header or 'ongoing-request="false"' not in restore_header:
                try:
                    s3_client.restore_object(
                        Bucket=bucket,
                        Key=s3_key,
                        RestoreRequest={
                            "Days": restore_days,
                            "GlacierJobParameters": {"Tier": restore_tier},
                        },
                    )
                    return DownloadResult(
                        ticket_no,
                        s3_key,
                        str(local_path),
                        "restore_requested",
                        None,
                    )
                except Exception as exc:  # noqa: BLE001
                    return DownloadResult(
                        ticket_no, s3_key, str(local_path), "restore_error", str(exc)
                    )

        output_dir.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(bucket, s3_key, str(local_path))
        return DownloadResult(ticket_no, s3_key, str(local_path), "downloaded", None)
    except Exception as exc:  # noqa: BLE001
        return DownloadResult(ticket_no, s3_key, str(local_path), "error", str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample complaints and download associated documents from S3."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=sqlite_path_from_db_url(settings.DB_URL),
        help="Path to SQLite grievance DB.",
    )
    parser.add_argument("--sample-size", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=directories.DATA / "samples" / "sample",
    )
    parser.add_argument("--bucket", type=str, default=settings.AWS_S3_DOCUMENTS)
    parser.add_argument("--region", type=str, default=settings.AWS_REGION)
    parser.add_argument(
        "--s3-prefix",
        type=str,
        default="",
        help="Optional S3 key prefix before ticket number, e.g. 'documents/'.",
    )
    parser.add_argument(
        "--download-documents",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing local files.",
    )
    parser.add_argument("--max-workers", type=int, default=12)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--restore-days", type=int, default=7)
    parser.add_argument(
        "--restore-tier",
        type=str,
        default="Standard",
        help="S3 restore tier: Expedited, Standard, or Bulk.",
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        raise FileNotFoundError(f"DB not found: {args.db_path}")

    logger.info("Starting sample run: size={}, seed={}", args.sample_size, args.seed)
    logger.info("Using DB at {}", args.db_path)
    logger.info("Output dir: {}", args.output_dir)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = args.output_dir / "documents"

    conn = sqlite3.connect(args.db_path)
    try:
        logger.info("Sampling ticket numbers")
        ticket_iter = iter_ticket_nos(conn)
        sample_tickets = reservoir_sample(ticket_iter, args.sample_size, args.seed)
        sample_tickets = sorted(set(sample_tickets))
        logger.info("Sampled {} unique tickets", len(sample_tickets))

        tickets_path = args.output_dir / "sample_tickets.txt"
        tickets_path.write_text("\n".join(sample_tickets) + "\n", encoding="utf-8")
        logger.info("Wrote ticket list to {}", tickets_path)

        complaints_parquet = args.output_dir / "complaints.parquet"
        actions_parquet = args.output_dir / "action_history.parquet"

        logger.info("Exporting complaints to {}", complaints_parquet)
        complaints_count = export_rows_to_parquet(
            conn, "complaints", sample_tickets, complaints_parquet, args.chunk_size
        )
        logger.info("Exported {} complaints", complaints_count)

        logger.info("Exporting action history to {}", actions_parquet)
        actions_count = export_rows_to_parquet(
            conn, "action_history", sample_tickets, actions_parquet, args.chunk_size
        )
        logger.info("Exported {} action history rows", actions_count)

        downloads: List[DownloadResult] = []
        if args.download_documents:
            logger.info(
                "Downloading documents from s3://{} (region={})",
                args.bucket,
                args.region,
            )
            s3_client = boto3.client("s3", region_name=args.region)
            def worker(ticket: str) -> DownloadResult:
                key = resolve_s3_key_by_prefix(
                    ticket,
                    s3_client,
                    args.bucket,
                    args.s3_prefix,
                )
                return download_one(
                    ticket,
                    key,
                    docs_dir,
                    s3_client,
                    args.bucket,
                    args.overwrite,
                    args.restore_days,
                    args.restore_tier,
                )

            with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                logger.info("Starting downloads with {} workers", args.max_workers)
                futures = [executor.submit(worker, t) for t in sample_tickets]
                for future in as_completed(futures):
                    downloads.append(future.result())
            logger.info("Completed {} download tasks", len(downloads))

            downloads_parquet = args.output_dir / "document_downloads.parquet"
            downloads_data = {
                "ticket_no": [d.ticket_no for d in downloads],
                "s3_key": [d.s3_key for d in downloads],
                "local_path": [d.local_path for d in downloads],
                "status": [d.status for d in downloads],
                "error": [d.error for d in downloads],
            }
            pq.write_table(pa.Table.from_pydict(downloads_data), downloads_parquet)
            logger.info("Wrote download report to {}", downloads_parquet)
        else:
            logger.info("Skipping document downloads")

        metadata = {
            "created_at": datetime.now().isoformat(),
            "db_path": str(args.db_path),
            "sample_size": args.sample_size,
            "seed": args.seed,
            "complaints_exported": complaints_count,
            "action_history_exported": actions_count,
            "bucket": args.bucket,
            "region": args.region,
            "download_documents": args.download_documents,
            "s3_prefix": args.s3_prefix,
            "documents_dir": str(docs_dir),
        }
        (args.output_dir / "sample_metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        logger.info("Wrote metadata")
    finally:
        conn.close()
        logger.info("Closed DB connection")


if __name__ == "__main__":
    main()
