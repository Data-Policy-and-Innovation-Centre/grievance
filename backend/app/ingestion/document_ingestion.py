import asyncio
import glob
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple
from io import BytesIO

import aiofiles
import httpx
from botocore.exceptions import ClientError
from loguru import logger
from more_itertools import chunked
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from app.config import (directories, resume_logging_to_console, settings,
                        stop_logging_to_console)
from app.db.crud import (get_complaint_by_ticket,
                         get_complaints_with_document_urls,
                         get_complaints_without_documents,
                         update_document_status)
from app.db.models import Complaint as ComplaintModel
from app.db.session import get_db
from app.ingestion.client import with_retry
from app.ingestion.schemas import Complaint
from app.s3service import S3Service


class DocumentService:
    """
    Async client for Document download service
    """

    def __init__(
        self, s3_bucket: str = settings.AWS_S3_DOCUMENTS, db: AsyncSession = None
    ):
        self.semaphore = asyncio.Semaphore(15)
        self.db = db
        self.async_lock = asyncio.Lock()
        if settings.ENV == "dev":
            self._create_local_folder()
        else:
            self.s3_service = S3Service(s3_bucket)

    def _create_local_folder(self):
        """
        Private function that creates a local folder if not exists
        """
        if not os.path.exists(settings.LOCAL_STORAGE_PATH):
            os.mkdir(settings.LOCAL_STORAGE_PATH)

    async def get_document_path(self, ticket_no: str, document_type: str) -> str:
        """
        Generates a local file path to store a document related to a complaint.

        Args:
        ticket_no (str): The unique identifier of the complaint.
        document_type (str): A string label indicating the type of document

        Returns:
            str: The full local file path where the document should be saved, or
                None if the complaint does not exist or an error occurs.
        """
        type_file_pattern = re.compile(r"~([a-zA-Z]*)$")
        complaint = await get_complaint_by_ticket(self.db, ticket_no)
        if complaint is None:
            logger.error(f"Complaint {ticket_no} does not exist in the database.")
            return None
        try:
            match = type_file_pattern.search(complaint.document_url)
            file_format = f".{match.group(1).lower()}" if match else ".bin"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticket_no}_{document_type}_{timestamp}{file_format}"
            if settings.ENV == "dev":
                return os.path.join(settings.LOCAL_STORAGE_PATH, filename)
            else:
                return filename
        except Exception as e:
            logger.error(f"Complaint {ticket_no} failed in get_document_path: {e}")
            return None

    def _document_already_downloaded_local(
        self, ticket_no: str, document_type: str, extension: str
    ) -> bool:
        """
        Checks whether a document with the given ticket number, document type,
        and file extension has already been downloaded. Regardless of the timestamp
        of the date when it was downloaded

        Args:
            ticket_no (str): The unique identifier of the complaint.
            document_type (str): The type of document (e.g., "complaint", "resolution").
            extension (str): The file extension to look for (e.g., "pdf", "docx").

        Returns:
            bool: True if a matching document file already existe, False otherwise
        """
        base_pattern = f"{ticket_no}_{document_type}_*.{extension.lower()}"
        full_pattern = os.path.join(settings.LOCAL_STORAGE_PATH, base_pattern)
        return len(glob.glob(full_pattern)) > 0

    def _document_already_downloaded_s3(
        self, ticket_no: str, document_type: str, extension: str
    ) -> bool:
        """
        Checks whether a document with the given ticket number, document type,
        and file extension has already been downloaded to S3. Regardless of the timestamp
        of the date when it was downloaded

        Args:
            ticket_no (str): The unique identifier of the complaint.
            document_type (str): The type of document (e.g., "complaint", "resolution").
            extension (str): The file extension to look for (e.g., "pdf", "docx").

        Returns:
            bool: True if a matching document file already exists in S3, False otherwise
        """
        prefix = f"{ticket_no}_{document_type}_"
        objects = self.s3_service.list_objects(prefix=prefix)

        for obj in objects:
            if obj["Key"].lower().endswith(f".{extension.lower()}"):
                return True

        return False

    def document_already_downloaded(
        self, ticket_no: str, document_type: str, extension: str
    ) -> bool:
        if settings.ENV == "dev":
            return self._document_already_downloaded_local(
                ticket_no, document_type, extension
            )

        return self._document_already_downloaded_s3(ticket_no, document_type, extension)

    @with_retry()
    async def download_document(
        self, complaint: ComplaintModel, document_type: str = "complaint"
    ) -> str:
        """
        Asynchronously downloads the document associated with a complaint, if not already downloaded.
        This method performs the following:
        - Validates the URL of the document
        - Constructs the expected local file path
        - Cheks if the document has already been dowloaded
        - Downloads and saves the document using an async HTTP Client

        Args:
            complaint (ComplaintModel): The complaint object containing the document URL and ticket number.
            document_type (str, optional): Label to distinguish types of documents. Defaults to "complaint".

        Returns:
            str: The full local file path where the document was saved, or None if the document was already downloaded
                or an error occurred during path generation or validation.
        """
        url, ticket_no = complaint.document_url, complaint.ticket_no

        if not url or not url.lower().startswith(
            ("http://", "https://")
        ):  # should also add "N/A"
            logger.warning(f"Complaint {ticket_no} does not have a valid document URL.")
            return None

        path = await self.get_document_path(ticket_no, document_type)

        if path is None:
            logger.warning(f"Failed to generate a path for complaint {ticket_no}")
            return None

        extension = os.path.splitext(path)[1][1:].lower()

        if self.document_already_downloaded(ticket_no, document_type, extension):
            logger.info(f"Document for complaint {ticket_no} already saved.")
            async with self.async_lock:
                complaint = await update_document_status(self.db, ticket_no, path, success=True, error=None)
                logger.info(f"Document status updated for complaint {ticket_no} to {complaint.document_downloaded}")
            return "s3"

        try:
            async with self.semaphore:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    if settings.ENV == "dev":
                        async with aiofiles.open(path, "wb") as f:
                            await f.write(response.content)
                    else:
                        file_obj = BytesIO(response.content)
                        self.s3_service.upload_fileobj(file_obj, path)
                        file_obj.close()

                logger.info(f"Downloaded document for complaint {ticket_no} to {path}")
            return path
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error downloading document for {ticket_no}: {error_msg}")
            raise

    async def batch_download_documents(
        self, complaints: List[ComplaintModel], batch_size: int = 500
    ) -> Dict[str, str]:
        """
        Batch download documents with optimized database operations.
        """
        results = {}
        batch_updates = []

        async def process(complaint: ComplaintModel) -> Tuple[str, str, Dict]:
            """Process a single document download."""
            try:
                path = await self.download_document(complaint)
                status = "success" if path else "skipped"

                # Return update data instead of calling update_document_status
                update_data = {
                    "ticket_no": complaint.ticket_no,
                    "local_path": path,
                    "success": (status == "success"),
                    "error": None,
                }

                return complaint.ticket_no, status, update_data

            except Exception as e:
                # Return error update data
                update_data = {
                    "ticket_no": complaint.ticket_no,
                    "local_path": None,
                    "success": False,
                    "error": str(e),
                }

                return complaint.ticket_no, "failed", update_data

        # Process all complaints concurrently
        tasks = [process(c) for c in complaints]

        counter = 0
        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Downloading documents",
            position=1,
            leave=False,
        ):
            ticket_no, status, update_data = await coro
            results[ticket_no] = status
            batch_updates.append(update_data)

            # Batch commit every batch_size tasks
            counter += 1
            if counter % batch_size == 0:
                await self._bulk_update_document_status(batch_updates)
                batch_updates = []  # Clear the batch

        # Commit any remaining updates
        if batch_updates:
            await self._bulk_update_document_status(batch_updates)

        return results

    async def batch_download_documents_in_chunks(
        self, complaints: List[ComplaintModel], chunk_size: int = 100
    ) -> Dict[str, str]:
        results = {}

        for i, complaint_chunk in enumerate(chunked(complaints, chunk_size), 1):
            logger.info(f" Processing chunk {i} ({len(complaint_chunk)} complaints)")
            chunk_result = await self.batch_download_documents(complaint_chunk)
            results.update(chunk_result)
            logger.success(f" Finished chunk {i}: {len(chunk_result)} processed")

        return results

    async def _bulk_update_document_status(self, updates: List[Dict]):
        """
        Bulk update document status using SQLAlchemy Core for maximum performance.
        """
        try:
            import pytz
            from sqlalchemy import case, update

            from app.db.models import Complaint as ComplaintModel

            time_zone = pytz.timezone("Asia/Kolkata")
            now = datetime.now(time_zone)

            # Create a single bulk update statement
            stmt = (
                update(ComplaintModel)
                .where(ComplaintModel.ticket_no.in_([u["ticket_no"] for u in updates]))
                .values(
                    local_document_path=case(
                        *[
                            (
                                ComplaintModel.ticket_no == u["ticket_no"],
                                u["local_path"],
                            )
                            for u in updates
                        ],
                        else_=ComplaintModel.local_document_path,
                    ),
                    document_downloaded=case(
                        *[
                            (ComplaintModel.ticket_no == u["ticket_no"], u["success"])
                            for u in updates
                        ],
                        else_=ComplaintModel.document_downloaded,
                    ),
                    document_download_date=case(
                        *[
                            (
                                ComplaintModel.ticket_no == u["ticket_no"],
                                (
                                    now
                                    if u["success"]
                                    else ComplaintModel.document_download_date
                                ),
                            )
                            for u in updates
                        ],
                        else_=ComplaintModel.document_download_date,
                    ),
                    document_download_error=case(
                        *[
                            (ComplaintModel.ticket_no == u["ticket_no"], u["error"])
                            for u in updates
                        ],
                        else_=ComplaintModel.document_download_error,
                    ),
                )
            )
            async with self.async_lock:
                result = await self.db.execute(stmt)
                await self.db.commit()

            logger.info(f"Bulk updated {result.rowcount} document statuses")

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error in bulk document status update: {e}")
            raise


async def main():
    db = next(get_db())
    doc_service = DocumentService(db=db)

    total_docs = get_complaints_with_document_urls(db)
    tickets = set([complaint.ticket_no for complaint in total_docs])

    pattern = re.compile(r"([A-Z]{2,4}[0-9]*)(_compliant)*")

    files_down = os.listdir(directories.DOCUMENTS)

    ticket_nos = set([re.search(pattern, file).group(0) for file in files_down])

    pending_tickets = tickets.difference(ticket_nos)

    print(len(tickets))
    print(len(ticket_nos))
    print(len(pending_tickets))

    pending_tickets = list(pending_tickets)

    sample_1000 = [
        get_complaint_by_ticket(db, ticket_no) for ticket_no in pending_tickets[:50000]
    ]
    logger.info(f"Starting downloading")
    stop_logging_to_console(mode="w")
    result = await doc_service.batch_download_documents_in_chunks(sample_1000, 100)
    resume_logging_to_console()
    logger.info(f"Finalizing downloading")


if __name__ == "__main__":
    asyncio.run(main())
