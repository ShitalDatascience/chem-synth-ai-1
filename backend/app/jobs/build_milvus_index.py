#!/usr/bin/env python3
"""Offline ingestion job: ChEMBL Postgres → RDKit fingerprint → Milvus Lite.

Pipeline (identical lifecycle to similarity query in ``milvus_service``):

  ``SMILES`` → :func:`rdkit_service.canonicalize_smiles` →
  ``fp_arr, _ = rdkit_service.morgan_fp(canon_smiles)`` → Milvus upsert

Only :mod:`app.services.rdkit_service` may compute Morgan fingerprints (radius=2, nBits=2048).

Usage:
    conda activate chemdev_clean
    python -m app.jobs.build_milvus_index
    python -m app.jobs.build_milvus_index --batch-size 2000 --reset
    python -m app.jobs.build_milvus_index --rebuild
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

CHECKPOINT_PATH = Path("data/milvus_ingest_checkpoint.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("build_milvus_index")


def _load_checkpoint() -> int:
    """Return last processed molregno (0 = start from beginning)."""
    if CHECKPOINT_PATH.exists():
        try:
            data = json.loads(CHECKPOINT_PATH.read_text())
            return int(data.get("last_molregno", 0))
        except Exception as e:
            print("ERROR:", e)
            raise
    return 0


def _save_checkpoint(last_molregno: int, total_inserted: int) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(
            {"last_molregno": last_molregno, "total_inserted": total_inserted},
            indent=2,
        )
    )


def run(batch_size: int = 1000, reset: bool = False, rebuild: bool = False) -> None:
    print("🚀 RUN FUNCTION ENTERED", flush=True)

    from dotenv import load_dotenv

    load_dotenv()

    try:
        from app.services.chembl_service import ChemblService
        from app.services.milvus_service import MilvusService
        from app.services import rdkit_service
    except Exception as e:
        print("❌ IMPORT FAILED:", str(e), flush=True)
        raise

    chembl = ChemblService()
    milvus = MilvusService()

    if rebuild:
        milvus.drop_collection()
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()
            logger.info("Removed checkpoint %s", CHECKPOINT_PATH)
        reset = True

    milvus.ensure_collection()

    last_molregno = 0 if reset else _load_checkpoint()

    if reset:
        logger.info("Reset flag: starting from molregno 0")
    else:
        logger.info("Resuming from molregno > %d", last_molregno)

    total_inserted = 0
    total_skipped = 0
    batch_num = 0
    t0 = time.monotonic()

    while True:
        batch_num += 1
        print(f"Batch {batch_num} fetching rows...", flush=True)

        rows = chembl.stream_smiles_for_ingestion(
            last_molregno=last_molregno,
            batch_size=batch_size,
        )

        if rows is None:
            print("❌ rows is None - DB issue", flush=True)
            return

        print("rows received:", len(rows), flush=True)

        if not rows:
            logger.info("No more rows. Ingestion complete.")
            break

        vectors = []

        for row in rows:
            smiles = row.get("canonical_smiles") or row.get("smiles_canonical")
            if not smiles:
                total_skipped += 1
                continue

            try:
                canon_smiles = rdkit_service.canonicalize_smiles(smiles)
                fp_arr, _ = rdkit_service.morgan_fp(canon_smiles)

                vectors.append(
                    {
                        "chembl_id": row["chembl_id"],
                        "molregno": row["molregno"],
                        "standard_inchi_key": row.get("standard_inchi_key") or "",
                        "smiles_canonical": canon_smiles,
                        "pref_name": row.get("pref_name") or "",
                        "mw_freebase": row.get("mw_freebase"),
                        "alogp": row.get("alogp"),
                        "psa": row.get("psa"),
                        "hba": row.get("hba"),
                        "hbd": row.get("hbd"),
                        "rtb": row.get("rtb"),
                        "qed_weighted": row.get("qed_weighted"),
                        "heavy_atoms": row.get("heavy_atoms"),
                        "aromatic_rings": row.get("aromatic_rings"),
                        "full_molformula": row.get("full_molformula"),
                        "np_likeness_score": row.get("np_likeness_score"),
                        "num_ro5_violations": row.get("num_ro5_violations"),
                        "ro3_pass": row.get("ro3_pass") or "",
                        "fp": fp_arr,
                    }
                )
            except Exception as exc:
                print("ERROR:", exc, flush=True)
                logger.warning("Skipping %s: %s", row.get("chembl_id"), exc)
                total_skipped += 1

        if vectors:
            inserted = milvus.upsert_vectors(vectors)
            total_inserted += inserted
            last_molregno = rows[-1]["molregno"]
            _save_checkpoint(last_molregno, total_inserted)
            elapsed = time.monotonic() - t0
            rate = total_inserted / elapsed if elapsed > 0 else 0
            logger.info(
                "Batch %d | inserted=%d | total=%d | skipped=%d | rate=%.0f/s",
                batch_num,
                inserted,
                total_inserted,
                total_skipped,
                rate,
            )
        else:
            last_molregno = rows[-1]["molregno"]
            logger.warning(
                "Batch %d: all %d rows skipped (no valid SMILES)",
                batch_num,
                len(rows),
            )

    logger.info(
        "Done. Total inserted=%d | Total skipped=%d | Elapsed=%.1fs",
        total_inserted,
        total_skipped,
        time.monotonic() - t0,
    )
    print("🏁 run() finished", flush=True)


if __name__ == "__main__":
    print("🔥 build_milvus_index STARTED", flush=True)

    parser = argparse.ArgumentParser(description="Build Milvus index from ChEMBL Postgres")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--reset", action="store_true", help="Ignore checkpoint and start over (keep Milvus rows)")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop Milvus collection, delete checkpoint, recreate index (fresh embeddings)",
    )
    args = parser.parse_args()

    run(
        batch_size=args.batch_size,
        reset=args.reset,
        rebuild=args.rebuild,
    )

    print("🏁 SCRIPT COMPLETED", flush=True)
