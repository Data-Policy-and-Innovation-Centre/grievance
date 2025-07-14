import asyncio
import glob
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

import aiofiles
import httpx
from botocore.exceptions import ClientError
from loguru import logger
from sqlalchemy.orm import Session
from tqdm import tqdm
from more_itertools import chunked

from app.config import settings, directories, resume_logging_to_console, stop_logging_to_console
from app.db.crud import (get_complaint_by_ticket,
                         get_complaints_with_document_urls,
                         get_complaints_without_documents,
                         update_document_status)
from app.db.session import get_db
from app.ingestion.client import with_retry
from app.ingestion.schemas import Complaint
from app.db.models import Complaint as ComplaintModel
from app.s3service import S3Service


class DocumentService:
    """
    Async client for Document download service
    """

    def __init__(self, s3_bucket: str = settings.AWS_S3_DOCUMENTS, db: Session = None):
        self.semaphore = asyncio.Semaphore(15)
        self.db = db or next(get_db())
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

    async def update_document_status_for_all_complaints(
        self, only_without_documents: bool = False
    ):
        """
        Update the document status for all complaints whose documents are already downloaded
        """
        logger.info(f"Updating document status for existing complaints in database")
        if only_without_documents:
            complaints = get_complaints_without_documents(self.db)
        else:
            complaints = get_complaints_with_document_urls(self.db)

        with tqdm(
            total=len(complaints),
            desc="Updating document status",
            position=1,
            leave=False,
        ) as pbar:
            for complaint in complaints:
                pbar.set_description(f"Processing {complaint.ticket_no}")
                path = self.get_document_path(complaint.ticket_no, "complaint")
                downloaded = any(
                    self.document_already_downloaded(
                        complaint.ticket_no, "complaint", ext
                    )
                    for ext in ["pdf", "jpeg", "docx", "doc", "png", "bin", "jpg"]
                )

                if downloaded:
                    update_document_status(
                        self.db, complaint.ticket_no, local_path=path, success=True
                    )
                    pbar.update(1)
                else:
                    await self.download_document(complaint)

                # TODO: Add as needed for other document types

    def get_document_path(self, ticket_no: str, document_type: str) -> str:
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
        complaint = get_complaint_by_ticket(self.db, ticket_no)
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
        self, complaint: Complaint, document_type: str = "complaint"
    ) -> str:
        """
        Asynchronously downloads the document associated with a complaint, if not already downloaded.
        This method performs the following:
        - Validates the URL of the document
        - Constructs the expected local file path
        - Cheks if the document has already been dowloaded
        - Downloads and saves the document using an async HTTP Client

        Args:
            complaint (Complaint): The complaint object containing the document URL and ticket number.
            document_type (str, optional): Label to distinguish types of documents. Defaults to "complaint".

        Returns:
            str: The full local file path where the document was saved, or None if the document was already downloaded
                or an error occurred during path generation or validation.
        """
        url, ticket_no = complaint.document_url, complaint.ticket_no

        if not url or not url.lower().startswith(("http://", "https://")):
            logger.warning(f"Complaint {ticket_no} does not have a valid document URL.")
            update_document_status(
                self.db,
                ticket_no,
                local_path=None,
                success=False,
                error=f"Error: Invalid URL for ticket {ticket_no}",
            )
            return None

        path = self.get_document_path(ticket_no, document_type)

        if path is None:
            logger.warning(f"Failed to generate a path for complaint {ticket_no}")
            update_document_status(
                self.db,
                ticket_no,
                local_path=None,
                success=False,
                error=f"Error: No document path for {ticket_no}",
            )
            return None

        extension = os.path.splitext(path)[1][1:].lower()

        if self.document_already_downloaded(ticket_no, document_type, extension):
            logger.info(f"Document for complaint {ticket_no} already saved.")
            return None

        try:
            async with self.semaphore:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    if settings.ENV == "dev":
                        async with aiofiles.open(path, "wb") as f:
                            await f.write(response.content)
                    else:
                        self.s3_service.upload_fileobj(response.content, path)
                logger.info(f"Downloaded document for complaint {ticket_no} to {path}")
                update_document_status(self.db, ticket_no, local_path=path, success=True)
            return path
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error downloading document for {ticket_no}: {error_msg}")
            update_document_status(
                self.db,
                ticket_no,
                local_path=None,
                success=False,
                error=f"Error: {error_msg}",
            )
            return "Error"

    async def batch_download_documents(self, complaints: List[Complaint]) -> Dict[str, str]:
        results = {}
        updated_complaints = []
        
        async def process(complaint: Complaint) -> Tuple[str, str]:
            try:
                path = await self.download_document(complaint)
                status = "success" if path else "skipped"
                updated = update_document_status(
                    self.db,
                    complaint.ticket_no,
                    local_path=path,
                    success=(status == "success"),
                )
                return complaint.ticket_no, status, updated
            except Exception as e:
                updated = update_document_status(
                    self.db,
                    complaint.ticket_no,
                    local_path=None,
                    success=False,
                    error=str(e),
                )
                return complaint.ticket_no, "failed", updated
            
        tasks = [process(c) for c in complaints]

        counter = 0
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Downloading documents", position=1, leave=False):
            ticket_no, status, updated = await coro
            # print(ticket_no)
            results[ticket_no] = status
            if updated:
                updated_complaints.append(updated)
            
            # Commits to db every 500 tasks
            counter += 1
            if counter % 500 == 0:
                self.db.commit()

        if updated_complaints:
            self.db.add_all(updated_complaints)
        self.db.commit()
        return results

    
    async def batch_download_documents_in_chunks(self, complaints: List[Complaint], chunk_size: int = 100) -> Dict[str, str]:
        results = {}

        for i, complaint_chunk in enumerate(chunked(complaints, chunk_size), 1):
            logger.info(f"📦 Processing chunk {i} ({len(complaint_chunk)} complaints)")
            chunk_result = await self.batch_download_documents(complaint_chunk)
            results.update(chunk_result)
            logger.success(f"✅ Finished chunk {i}: {len(chunk_result)} processed")

        return results

async def main():
    db = next(get_db())
    doc_service = DocumentService(db = db)

    total_docs = get_complaints_with_document_urls(db)
    tickets = set([complaint.ticket_no for complaint in total_docs])

    pattern = re.compile(r'([A-Z]{2,4}[0-9]*)(_compliant)*')

    files_down = os.listdir(directories.DOCUMENTS)

    ticket_nos = set([re.search(pattern, file).group(0) for file in files_down])

    pending_tickets = tickets.difference(ticket_nos)
    
    print(len(tickets))
    print(len(ticket_nos))
    print(len(pending_tickets))

    pending_tickets = list(pending_tickets)

    sample_1000 = [get_complaint_by_ticket(db, ticket_no) for ticket_no in pending_tickets[:50000]]
    logger.info(f"Starting downloading")
    stop_logging_to_console(mode="w")
    result = await doc_service.batch_download_documents_in_chunks(sample_1000,100)
    resume_logging_to_console()
    logger.info(f"Finalizing downloading")
    
    
if __name__ == "__main__":
    asyncio.run(main())