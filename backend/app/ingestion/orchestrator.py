import json
import boto3
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from .client import JanasunaniAPIClient
from .schemas import validate, Complaint, District, ActionHistory, validate_action_history
from ..db.models import District as DistrictModel
from ..db.crud import (
    bulk_load_districts,
    bulk_load_complaints,
    bulk_load_action_histories,
    filter_complaints_api_request,
    record_complaint_api_request_success,
    mark_complaints_api_request_failed,
    get_all_complaints,
    get_tickets_needing_action_history,
    record_action_history_api_request_success,
    mark_action_history_api_request_failed,
    get_complaints_without_documents
)
from ..db.session import get_db
from . import OFFICE, STATUS
from app.config import settings, stop_logging_to_console, resume_logging_to_console
import asyncio
from more_itertools import chunked
from .document_ingestion import DocumentService
from typing import List, Dict, Tuple, Coroutine
from tqdm.asyncio import tqdm
import sys
import argparse

class IngestionOrchestrator:
    def __init__(self, db: Session, semaphore_value: int = 5):
        self.client = JanasunaniAPIClient()
        self.s3 = boto3.client('s3')
        self.bucket_name = 'grievance-raw-data'
        self.db = db
        self.semaphore = asyncio.Semaphore(semaphore_value)
        self.doc_service = DocumentService(db=self.db)

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

            if action_history is None:
                logger.warning(f"No action history received for ticket={ticket_no}")
                mark_action_history_api_request_failed(self.db, ticket_no)
                return []
            
            record_action_history_api_request_success(self.db, ticket_no, len(action_history))

            action_history_validated = validate_action_history(items=action_history, ticket_no=ticket_no, dict_mode=False)

            # Store data in database using CRUD operations
            stored_action_history = bulk_load_action_histories(self.db, action_history_validated)
            logger.info(f"Successfully stored {len(stored_action_history)} action history in database")

            return action_history_validated
        except Exception as e:
            logger.error(f"Error ingesting action history failed for ticket={ticket_no}: {e}")
            mark_action_history_api_request_failed(self.db, ticket_no)
            return []
        
    async def ingest_documents(self, complaints: List[Complaint], doc_service: DocumentService) -> Dict[str, str]:
        '''Ingest documents data'''
        results = await doc_service.batch_download_documents(complaints)
        return results

# Wrap each task to update the tqdm bar when done
async def track_with_progress(coros: List[Coroutine], desc: str = "Processing", position: int = 0):
    results = []
    total = len(coros)

    # tqdm.asyncio is smart about async display updates
    with tqdm(total=total, desc=desc, ncols=100, position=position) as pbar:
        async def wrapped(coro):
            try:
                result = await coro
                return result
            finally:
                pbar.update(1)

        tasks = [wrapped(coro) for coro in coros]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return results

async def run_ingestion_service(force_params: List[Tuple[int, int, int, int]] = None,
                                ingest_complaints: bool = True,
                                ingest_documents: bool = True,
                                ingest_action_history: bool = True):
    """Main async ingestion service runner."""
    days_threshold = 7
    max_retries = 1
    try:                

        db = next(get_db())
        orchestrator = IngestionOrchestrator(db,5)
        
        # Load districts from database if exists or ingest
        districts = db.query(DistrictModel).all()
        if not districts:
            districts = orchestrator.ingest_districts() 

        # Generate initial set of all possible combinations
        params = [(year, district.dist_id, status, office) 
                       for year in [2025] # TODO: change to range(2021, datetime.now().year)
                       for district in districts 
                       for status in STATUS.keys() 
                       for office in OFFICE.keys()]
        
        if ingest_complaints:
            logger.info(f"Num. possible complaint requests: {len(params)}")
            params = [
                param for param in params if not filter_complaints_api_request(db, *param, days_threshold=days_threshold, failure_threshold=max_retries)
            ]
            
            if force_params:
                params.extend(force_params)

            logger.info(f"Total complaint requests to process: {len(params)}")

            stop_logging_to_console(mode='w')

            try:
                tasks = [orchestrator.ingest_complaints(*param) for param in params]
                complaints = await track_with_progress(tasks, desc="Ingesting complaints")
                success_count = 0
                failure_count = 0
                for result, (year, dist_id, status, office) in zip(complaints, params):
                    if isinstance(result, list) and len(result) > 0:
                        logger.info(f"Successfully ingested {len(result)} complaints for year={year}, dist={dist_id}, status={status}, office={office}")
                        record_complaint_api_request_success(db, year, dist_id, status, office, len(result))
                        success_count += 1
                    elif isinstance(result, Exception) or len(result) == 0:
                        logger.error(f"Failed to process year={year}, dist={dist_id}, status={status}, office={office}: {result}")
                        mark_complaints_api_request_failed(db, year, dist_id, status, office)
                        failure_count += 1
                    else:
                        logger.debug(f"Unknown result type: {type(result)}")
                resume_logging_to_console()
                logger.info(f"Completed {len(complaints)} complaint ingestion tasks\n \t Success: {success_count}\n \t Failure: {failure_count}")
            except Exception as e:
                logger.error(f"Error in complaint ingestion: {e}")

        # Ingest documents and action history for each complaint
        if ingest_documents:
            try:
                complaints = get_complaints_without_documents(db)
                if settings.ENV == "dev":
                    logger.info(f"Processing documents for {len(complaints)} complaints with local path {settings.LOCAL_STORAGE_PATH}")
                elif settings.ENV == "main":
                    logger.info(f"Processing documents for {len(complaints)} complaints with s3 path {settings.AWS_S3_DOCUMENTS}")
                else:
                    raise ValueError(f"Invalid environment: {settings.ENV}")
                
                stop_logging_to_console()
                doc_tasks = [
                    orchestrator.ingest_documents(chunk, orchestrator.doc_service)
                    for chunk in chunked(complaints, 10)
                ]
                doc_results = await track_with_progress(doc_tasks, desc="Ingesting documents")
                await orchestrator.doc_service.update_document_status_for_all_complaints(only_without_documents=True)
                resume_logging_to_console()
                logger.info(f"Completed {len(doc_results)} document ingestion tasks")
            except Exception as e:
                logger.error(f"Error in document ingestion: {e}")

        if ingest_action_history:
            try:
                ticket_numbers = get_tickets_needing_action_history(db)

                logger.info(f"Processing action history for {len(ticket_numbers)} complaints")
                action_tasks = [
                    orchestrator.ingest_action_history(ticket_no)
                    for ticket_no in ticket_numbers
                ]
                stop_logging_to_console()
                action_result = await track_with_progress(action_tasks, desc="Ingesting actions")
                resume_logging_to_console()
                logger.info(f"Completed {len(action_result)} action ingestion tasks")
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


def main(args):
    parser = argparse.ArgumentParser(description='Grievance Data Ingestion Service')
    parser.add_argument('--force-params', action='store_true', 
                       help='Force ingestion with default parameters')
    parser.add_argument('--ingest-complaints', action='store_true', 
                       help='Ingest complaint data')
    parser.add_argument('--ingest-documents', action='store_true', 
                       help='Ingest document data')
    parser.add_argument('--ingest-action-history', action='store_true', 
                       help='Ingest action history data')
    
    args = parser.parse_args(args)
    
    force_params = args.force_params
    ingest_complaints = args.ingest_complaints
    ingest_documents = args.ingest_documents
    ingest_action_history = args.ingest_action_history
    asyncio.run(run_ingestion_service(force_params, ingest_complaints, ingest_documents, ingest_action_history))
    
if __name__ == "__main__":
    main(sys.argv[1:])