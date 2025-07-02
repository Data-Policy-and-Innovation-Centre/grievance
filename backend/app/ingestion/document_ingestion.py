import re
import os
import asyncio
import httpx
import aiofiles
import glob
from typing import List, Dict
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.crud import get_complaint_by_ticket, update_document_status
from app.config import settings
from app.ingestion.schemas import Complaint
from app.ingestion.client import with_retry

class DocumentService:
    def __init__(self, storage_type: str = "local", s3_bucket: str = settings.AWS_S3_BUCKET_NAME, db: Session = None):
        self.storage_type = storage_type
        self.s3 = s3_bucket
        self.semaphore = asyncio.Semaphore(5)
        self.db = db or (next(get_db()) if storage_type == "local" else None)
        if storage_type == "local":
            self.__create_local_folder()
    
    def __create_local_folder(self):
        if not os.path.exists(settings.LOCAL_STORAGE_PATH):
            os.mkdir(settings.LOCAL_STORAGE_PATH)

    def get_document_path(self, ticket_no: str, document_type: str) -> str:
        type_file_pattern = re.compile(r'~([a-zA-Z]*)$') 
        complaint = get_complaint_by_ticket(self.db, ticket_no)
        if complaint is None:
            logger.error(f"Complaint {ticket_no} does not exist in the database.")
            return None
        try:
            match = type_file_pattern.search(complaint.document_url)
            file_format = f".{match.group(1).lower()}" if match else ".bin"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticket_no}_{document_type}_{timestamp}{file_format}"
            return os.path.join(settings.LOCAL_STORAGE_PATH, filename)
        except Exception as e:
            logger.error(f"Complaint {ticket_no} failed in get_document_path: {e}")
            return None

    def document_already_downloaded(self, ticket_no: str, document_type: str, extension: str) -> bool:
        base_pattern = f"{ticket_no}_{document_type}_*.{extension.lower()}"
        full_pattern = os.path.join(settings.LOCAL_STORAGE_PATH, base_pattern)
        return len(glob.glob(full_pattern)) > 0

    @with_retry()
    async def download_document(self, complaint: Complaint, document_type: str = "complaint") -> str:
        url, ticket_no = complaint.document_url, complaint.ticket_no

        if not url or not url.lower().startswith(("http://", "https://")):
            logger.info(f"Complaint {ticket_no} does not have a valid document URL.")
            return None
        
        path = self.get_document_path(ticket_no, document_type)

        if path is None:
            logger.warning(f"Failed to generate a path for complaint {ticket_no}")
            return None
        
        extension = os.path.splitext(path)[1][1:].lower()

        if self.document_already_downloaded(ticket_no, document_type, extension):
            logger.info(f"Document for complaint {ticket_no} already saved.")
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                async with aiofiles.open(path, 'wb') as f:
                    await f.write(response.content)
            logger.info(f"Downloaded document for complaint {ticket_no} to {path}")
            return path
        except Exception as e:
            logger.error(f"Error downloading document for {ticket_no}: {e}")
            raise

    async def batch_download_documents(self, complaints: List[Complaint]) -> Dict[str, str]:
        results = {}
        for complaint in complaints:
            try:
                path = await self.download_document(complaint)
                if path:
                    update_document_status(self.db, complaint.ticket_no, local_path=path, success=True)
                    results[complaint.ticket_no] = "success"
                else:
                    results[complaint.ticket_no] = "skipped"
            except Exception as e:
                update_document_status(self.db, complaint.ticket_no, local_path="", success=False, error=str(e))
                results[complaint.ticket_no] = "failed"
        self.db.commit()
        return results