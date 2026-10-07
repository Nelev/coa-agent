"""Where a run's PDF comes from: an upload, or one of the 8 sample CoAs.

Both end the same way: a file at uploads/<pdf_id>.pdf under a generated id,
never a name the client chose, which is all `read_coa` and the viewer ever see.
"""

import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from schema import FileTooLarge, NotAPdf, NotFound, Sample
from settings import MAX_UPLOAD_BYTES, get_settings
from tools.data import DATASET_DIR, load

PDF_MAGIC = b"%PDF-"


def _destination() -> tuple[str, Path]:
    uploads = get_settings().uploads_dir
    uploads.mkdir(parents=True, exist_ok=True)
    pdf_id = uuid.uuid4().hex
    return pdf_id, uploads / f"{pdf_id}.pdf"


async def save_upload(file: UploadFile) -> str:
    """Store an uploaded PDF and return its id. Checked by size and header; at
    most one byte over the limit is ever read."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLarge
    if not data.startswith(PDF_MAGIC):
        raise NotAPdf
    pdf_id, path = _destination()
    await asyncio.to_thread(path.write_bytes, data)
    return pdf_id


def list_samples() -> list[Sample]:
    return [
        Sample(
            file=row["file"],
            scenario=int(row["file"].split("_")[1]),
            title=row["title"],
        )
        for row in load("expected")
    ]


async def copy_sample(file: str) -> str:
    """Copy a sample CoA into the uploads and return its id. Only names in
    expected.csv are accepted, so the argument can't reach another path."""
    if file not in {s.file for s in list_samples()}:
        raise NotFound("Unknown sample")
    pdf_id, path = _destination()
    await asyncio.to_thread(shutil.copyfile, DATASET_DIR / "coa" / file, path)
    return pdf_id
