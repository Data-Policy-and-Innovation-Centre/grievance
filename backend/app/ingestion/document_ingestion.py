import re
import os
import asyncio
import httpx
import aiofiles
from typing import List, Dict
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.crud import get_complaint_by_ticket, update_document_status
from app.config import settings
from app.ingestion.schemas import Complaint

class DocumentService:
    def __init__(self, storage_type: str = "local", s3_bucket: str = settings.AWS_S3_BUCKET_NAME, db: Session = None):
        self.storage_type = storage_type
        self.s3 = s3_bucket
        self.semaphore = asyncio.Semaphore(5)
        self.db = db or (next(get_db()) if storage_type == "local" else None)

    def get_document_path(self, ticket_no: str, document_type: str) -> str:
            type_file_pattern = re.compile(r"\~\w{3}$") 
            complaint = get_complaint_by_ticket(self.db, ticket_no)
            if complaint is None:
                logger.error(f"Complaint {ticket_no} does not exist in the database.")
                return None
            try:
                file_format = re.findall(type_file_pattern, complaint.document_url)[0]
                file_format = "." + file_format[1:]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{ticket_no}_{document_type}_{timestamp}{file_format}"
                return os.path.join(settings.LOCAL_STORAGE_PATH, filename)
            except IndexError as e:
                logger.error(f"Complaint {ticket_no} with no valid file type: {e}")
                return None

    def document_exists(self, ticket_no: str, document_type: str) -> bool:
        path = self.get_document_path(ticket_no, document_type)
        return os.path.exists(path)

    async def download_document(self, url: str, ticket_no: str, document_type: str = "complaint") -> str:
        path = self.get_document_path(ticket_no, document_type)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                async with aiofiles.open(path, 'wb') as f:
                    await f.write(response.content)
            return path
        except Exception as e:
            logger.error(f"Error downloading document for {ticket_no}: {e}")
            raise

    async def batch_download_documents(self, complaints: List[Complaint]) -> Dict[str, str]:
        results = {}
        async with self.db as db:
            for complaint in complaints:
                try:
                    path = await self.download_document(complaint.document_url, complaint.ticket_no)
                    update_document_status(db, complaint.ticket_no, local_path=path, success=True)
                    results[complaint.ticket_no] = "success"
                except Exception as e:
                    update_document_status(db, complaint.ticket_no, local_path="", success=False, error=str(e))
                    results[complaint.ticket_no] = "failed"
        return results