import json
import boto3
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from .client import JanasunaniAPIClient, JanasunaniAPIError
from .schemas import validate, Complaint, District, ActionHistory, validate_action_history
from ..db.crud import (
    bulk_load_districts,
    bulk_load_complaints,
    bulk_load_action_histories
)
from ..db.session import get_db
from . import OFFICE, STATUS
from app.config import settings
import asyncio
from more_itertools import chunked
from .document_ingestion import DocumentService
from typing import List, Dict

class IngestionOrchestrator:
    def __init__(self, db: Session, semaphore_value: int = 5):
        self.client = JanasunaniAPIClient()
        self.s3 = boto3.client('s3')
        self.bucket_name = 'grievance-raw-data'
        self.db = db
        self.semaphore = asyncio.Semaphore(semaphore_value)
        self.doc_service = DocumentService(storage_type = "local", db = self.db)

    def _store_in_s3(self, data: dict, prefix: str):
        """Store raw data in S3 with timestamp."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        key = f"{prefix}/{timestamp}.json"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(data),
                ContentType='application/json'
            )
            logger.info(f"Successfully stored data in S3: {key}")
        except Exception as e:
            logger.error(f"Error storing data in S3: {e}")
            raise

    def ingest_districts(self):
        """Ingest district data."""
        try:
            districts = self.client.get_districts()
            districts_validated = validate(districts, District, dict_mode=False)
            
            # Store data in database using CRUD operations
            stored_districts = bulk_load_districts(self.db, districts_validated)
            logger.info(f"Successfully stored {len(stored_districts)} districts in database")
            
            return districts_validated
        except Exception as e:
            logger.error(f"Error ingesting districts: {e}")
            raise

    async def ingest_complaints(self, year: int, distId: int, status: int, office: int) -> list[Complaint]:
        """Ingest complaint data."""
        try:
            complaints = await self.client.get_complaints(year, distId, status, office, self.semaphore)
            if complaints is None:
                logger.warning(f"No complaints received for year={year}, dist={distId}, status={status}, office={office}")
                return []
            complaints_validated = validate(complaints, Complaint, dict_mode=False)
            
            # Store data in database using CRUD operations
            stored_complaints = bulk_load_complaints(self.db, complaints_validated)
            logger.info(f"Successfully stored {len(stored_complaints)} complaints in database")
            
            return complaints_validated
        except Exception as e:
            logger.error(f"Complaint ingestion failed for dist={distId}, year={year}, status={status}, office={office}: {e}")
            return []

    async def ingest_action_history(self, ticket_no: str) -> list[ActionHistory]:
        """Ingest action history data."""
        try:
            action_history = await self.client.get_action_history(ticket_no, self.semaphore)
            action_history_validated = validate_action_history(items=action_history, ticket_no=ticket_no, dict_mode=False)

            # Store data in database using CRUD operations
            stored_action_history = bulk_load_action_histories(self.db, action_history_validated)
            logger.info(f"Successfully stored {len(stored_action_history)} action history in database")

            return action_history_validated
        except Exception as e:
            logger.error(f"Error ingesting action history failed for ticket={ticket_no}: {e}")
            return []
        
    async def ingest_documents(self, complaints: List[Complaint], doc_service: DocumentService) -> Dict[str, str]:
        '''Ingest documents data'''
        results = await doc_service.batch_download_documents(complaints)
        return results
            

async def run_ingestion_service():
    """Main async ingestion service runner."""
    try:
        db = next(get_db())
        orchestrator = IngestionOrchestrator(db,5)
        doc_service = DocumentService(storage_type="local", db = db)
        
        # Ingest districts
        districts = orchestrator.ingest_districts()

        # Ingest complaints for each year, district, status and office
        params = [(year, district.dist_id, status, office) for year in range(2024, datetime.now().year) 
                  for district in districts[:1] for status in [2] 
                  for office in [2]]
        logger.info(f"Total complaint requests to process: {len(params)}")
        
        try:
            tasks = [orchestrator.ingest_complaints(*param) for param in params]
            complaints = await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Completed {len(complaints)} complaint ingestion tasks")
        except Exception as e:
            logger.error(f"Error in complaint ingestion: {e}")
        
        # Ingest action history for each complaint
        try:
            flattened_complaints = [complaint for sublist in complaints if isinstance(sublist, list) for complaint in sublist]

            logger.info(f"Processing documents for {len(flattened_complaints)} complaints")
            for chunk in chunked(flattened_complaints, 10):
                tasks = [orchestrator.ingest_documents(chunk, doc_service)]
                doc_results = await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Completed {len(doc_results)} document ingestion tasks")

            logger.info(f"Processing action history for {len(flattened_complaints)} complaints")
            for chunk in chunked(flattened_complaints, 5):
                tasks = [orchestrator.ingest_action_history(complaint.ticket_no) for complaint in chunk]
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in action history ingestion: {e}")
        
        logger.info("Data ingestion completed successfully")
        return {
            'statusCode': 200,
            'body': json.dumps('Data ingestion completed successfully')
        }
        
    except Exception as e:
        logger.error(f"Error in ingestion service: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
    finally:
        db.close()
    
if __name__ == "__main__":
    asyncio.run(run_ingestion_service())