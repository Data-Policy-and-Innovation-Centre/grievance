from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.models import District as DistrictModel
from app.ingestion.orchestrator import run_ingestion_service


@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    Set up the test environment for CRUD tests.
    This ensures we use the real OFFICE constant for these tests.
    """
    import sys

    from app.ingestion import OFFICE as REAL_OFFICE
    from app.ingestion import schemas

    # Store the original OFFICE if it exists
    original_office = getattr(schemas, "OFFICE", None)

    # Set the real OFFICE constant
    sys.modules["app.ingestion.schemas"].OFFICE = REAL_OFFICE

    yield

    # Restore the original OFFICE if it existed
    if original_office is not None:
        sys.modules["app.ingestion.schemas"].OFFICE = original_office
    elif hasattr(schemas, "OFFICE"):
        delattr(schemas, "OFFICE")


# Test database setup
@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a fresh database for each test."""
    # Create in-memory SQLite database for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create a new session for the test
    TestingAsyncSessionLocal = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with TestingAsyncSessionLocal() as session:
        yield session


@pytest.fixture
def sample_district_data():
    """Sample district data for testing."""
    return [
        {
            "dist_id": 1,
            "dist_name": "Test District 1",
        },
        {
            "dist_id": 2,
            "dist_name": "Test District 2",
        },
    ]


@pytest.fixture
def sample_complaint_data():
    """Sample complaint data for testing."""
    return [
        {
            "ticketNumber": "T123",
            "petitionerName": "John Doe",
            "petitionerMobile": "1234567890",
            "petitionerEmail": "john@example.com",
            "grievanceSubject": "Road issue",
            "Document": "www.example.com",
            "intOfficeId": 1,
            "officeNAme": "Office of the Chief Minister",
            "RecievedByOfficerName": "Officer X",
            "intDistId": 1,
            "districtName": "District 1",
            "intBlockId": 1,
            "blockName": "Block A",
            "Address": "123 Main St",
            "modeName": "Online",
            "disbilityName": None,
            "StatusName": "Pending",
            "govtTicket": "Yes",
            "CreatedOn": "2024-06-01T12:00:00",
            "taggedTo": None,
            "taggedByName": None,
            "taggedDate": None,
            "CategoryId": 1,
            "category": "Infrastructure",
            "DepartmentId": 1,
            "deptName": "PWD",
            "SubCategoryId": 1,
            "Subcategory": "Road",
            "stateName": "StateX",
            "genderName": "Male",
            "transferStatus": "None",
            "mostUrgent": "No",
            "pendingwithName": None,
            "assignedOn": "2024-06-01T13:00:00",
            "escalationDate": None,
            "isSelfAssign": "No",
            "ResolvedOn": None,
            "resolvedBy": "Officer Y",
            "benefitted": "No",
            "trackingId": "track-123",
        }
    ]


@pytest.fixture
def sample_action_history_data():
    """Sample action history data for testing."""
    return [
        {
            "ticketNumber": "T123",
            "action_taken_date": "2024-03-20T10:00:00",
            "action_taken_remark": "Complaint received",
            "action_taken_by": "System",
            "action_status": "Pending",
            "complaint_status_with_authority": "Lodu",
            "trackingId": "track-123",
        }
    ]


async def async_gen_single(value):
    yield value


class TestRunIngestionService:
    """Integration tests for run_ingestion_service function."""

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.record_complaint_api_request_success")
    @patch("app.ingestion.orchestrator.mark_complaints_api_request_failed")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_complaints_only(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_mark_failed,
        mock_record_success,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
        sample_complaint_data,
    ):
        """Test run_ingestion_service with complaints ingestion only."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock complaint ingestion
            mock_orchestrator.ingest_complaints = AsyncMock(
                return_value=sample_complaint_data
            )

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]

            assert mock_orchestrator.ingest_complaints.call_count > 0

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.get_complaints_without_documents")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_documents_only(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_get_complaints,
        mock_get_db,
        db_session,
        sample_district_data,
        sample_complaint_data,
    ):
        """Test run_ingestion_service with documents ingestion only."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock complaints without documents
        from app.ingestion.schemas import Complaint as ComplaintSchema

        complaints = [
            ComplaintSchema(**complaint) for complaint in sample_complaint_data
        ]

        mock_get_complaints.side_effect = [1, complaints]

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock document ingestion
            mock_orchestrator.ingest_documents = AsyncMock(
                return_value={"T123": "success"}
            )

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=False,
                ingest_documents=True,
                ingest_action_history=False,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]
            assert mock_stop_logging.call_count > 0
            assert mock_resume_logging.call_count > 0

            # Verify document ingestion was called
            assert mock_orchestrator.ingest_documents.call_count > 0

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.get_tickets_needing_action_history")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_action_history_only(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_get_tickets,
        mock_get_db,
        db_session,
        sample_district_data,
        sample_action_history_data,
    ):
        """Test run_ingestion_service with action history ingestion only."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock tickets needing action history
        mock_get_tickets.return_value = ["T123", "T124"]

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock action history ingestion
            from app.ingestion.schemas import ActionHistory

            action_history = [
                ActionHistory(**action) for action in sample_action_history_data
            ]
            mock_orchestrator.ingest_action_history = AsyncMock(
                return_value=action_history
            )

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=False,
                ingest_documents=False,
                ingest_action_history=True,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]

            # Verify action history ingestion was called
            assert mock_orchestrator.ingest_action_history.call_count == 2

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.record_complaint_api_request_success")
    @patch("app.ingestion.orchestrator.mark_complaints_api_request_failed")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_with_force_params(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_mark_failed,
        mock_record_success,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
        sample_complaint_data,
    ):
        """Test run_ingestion_service with force parameters."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock complaint ingestion
            mock_orchestrator.ingest_complaints = AsyncMock(
                return_value=sample_complaint_data
            )

            # Execute with force parameters
            force_params = [(2024, 1, 1, 1), (2024, 2, 1, 1)]
            result = await run_ingestion_service(
                force_params=force_params,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]

            # Verify complaint ingestion was called for both regular and force params
            assert mock_orchestrator.ingest_complaints.call_count >= len(force_params)

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.record_complaint_api_request_success")
    @patch("app.ingestion.orchestrator.mark_complaints_api_request_failed")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_mixed_success_failure(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_mark_failed,
        mock_record_success,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
        sample_complaint_data,
    ):
        """Test run_ingestion_service with mixed success and failure scenarios."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock complaint ingestion with mixed results
            mock_orchestrator.ingest_complaints = AsyncMock(
                side_effect=[
                    sample_complaint_data,  # Success
                    Exception("API Error"),  # Failure
                    [],  # Empty result
                ]
            )

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]

            # Verify success and failure were recorded
            assert mock_record_success.call_count >= 1
            assert mock_mark_failed.call_count >= 1

    @patch("app.ingestion.orchestrator.get_db")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_database_error(self, mock_get_db):
        """Test run_ingestion_service when database connection fails."""
        # Mock database to raise exception
        mock_get_db.side_effect = Exception("Database connection failed")

        # Execute
        result = await run_ingestion_service(
            force_params=None,
            ingest_complaints=True,
            ingest_documents=False,
            ingest_action_history=False,
        )

        # Verify
        assert result["statusCode"] == 500
        assert "Error: Database connection failed" in result["body"]

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_no_districts_in_db(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
    ):
        """Test run_ingestion_service when no districts exist in database."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion (no districts in DB, so this should be called)
            districts = [DistrictModel(**district) for district in sample_district_data]
            mock_orchestrator.ingest_districts = AsyncMock(return_value=districts)

            # Mock complaint ingestion
            mock_orchestrator.ingest_complaints = AsyncMock(return_value=[])

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]

            # Verify district ingestion was called
            mock_orchestrator.ingest_districts.assert_called_once()

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_all_filters_blocked(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
    ):
        """Test run_ingestion_service when all requests are filtered out."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock filter to block all requests
        mock_filter.return_value = True

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            districts = [DistrictModel(**district) for district in sample_district_data]
            mock_orchestrator.ingest_districts = AsyncMock(return_value=districts)

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify
            assert result["statusCode"] == 200
            assert "Data ingestion completed successfully" in result["body"]

            # Verify no complaint ingestion was called
            mock_orchestrator.ingest_complaints.assert_not_called()

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.record_complaint_api_request_success")
    @patch("app.ingestion.orchestrator.mark_complaints_api_request_failed")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_all_components(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_mark_failed,
        mock_record_success,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
        sample_complaint_data,
        sample_action_history_data,
    ):
        """Test run_ingestion_service with all components enabled."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock other required functions
        with patch(
            "app.ingestion.orchestrator.get_complaints_without_documents"
        ) as mock_get_complaints, patch(
            "app.ingestion.orchestrator.get_tickets_needing_action_history"
        ) as mock_get_tickets:

            # Mock complaints without documents
            from app.ingestion.schemas import Complaint as ComplaintModel

            complaints = [
                ComplaintModel(**complaint) for complaint in sample_complaint_data
            ]
            mock_get_complaints.side_effect = [1, complaints]

            # Mock tickets needing action history
            mock_get_tickets.return_value = ["T123"]

            # Mock orchestrator methods
            with patch(
                "app.ingestion.orchestrator.IngestionOrchestrator"
            ) as mock_orchestrator_class:
                mock_orchestrator = MagicMock()
                mock_orchestrator_class.return_value = mock_orchestrator

                # Mock district ingestion
                mock_orchestrator.ingest_districts.return_value = districts

                # Mock complaint ingestion
                mock_orchestrator.ingest_complaints = AsyncMock(
                    return_value=sample_complaint_data
                )

                # Mock document ingestion
                mock_orchestrator.ingest_documents = AsyncMock(
                    return_value={"T123": "success"}
                )

                # Mock action history ingestion
                from app.ingestion.schemas import ActionHistory

                action_history = [
                    ActionHistory(**action) for action in sample_action_history_data
                ]
                mock_orchestrator.ingest_action_history = AsyncMock(
                    return_value=action_history
                )

                # Execute
                result = await run_ingestion_service(
                    force_params=None,
                    ingest_complaints=True,
                    ingest_documents=True,
                    ingest_action_history=True,
                )

                # Verify
                assert result["statusCode"] == 200
                assert "Data ingestion completed successfully" in result["body"]

                # Verify all components were called
                assert mock_orchestrator.ingest_complaints.call_count > 0
                assert mock_orchestrator.ingest_documents.call_count > 0
                assert mock_orchestrator.ingest_action_history.call_count == 1

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_logging_management(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
    ):
        """Test that logging is properly managed during ingestion."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock complaint ingestion
            mock_orchestrator.ingest_complaints = AsyncMock(return_value=[])

            # Execute
            await run_ingestion_service(
                force_params=None,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify logging was properly managed
            mock_stop_logging.assert_called_once()
            mock_resume_logging.assert_called_once()

            # Verify the calls were made with correct parameters
            stop_call_args = mock_stop_logging.call_args
            assert stop_call_args[1]["mode"] == "w"
            assert "ingest_complaints.log" in str(stop_call_args[1]["filename"])

    @patch("app.ingestion.orchestrator.get_db")
    @patch("app.ingestion.orchestrator.filter_complaints_api_request")
    @patch("app.ingestion.orchestrator.stop_logging_to_console")
    @patch("app.ingestion.orchestrator.resume_logging_to_console")
    @pytest.mark.asyncio
    async def test_run_ingestion_service_exception_handling(
        self,
        mock_resume_logging,
        mock_stop_logging,
        mock_filter,
        mock_get_db,
        db_session,
        sample_district_data,
    ):
        """Test exception handling during ingestion."""
        # Mock database session
        mock_get_db.return_value = async_gen_single(db_session)

        # Mock district data
        districts = [DistrictModel(**district) for district in sample_district_data]
        db_session.add_all(districts)
        await db_session.commit()

        # Mock filter to allow all requests
        mock_filter.return_value = False

        # Mock orchestrator methods
        with patch(
            "app.ingestion.orchestrator.IngestionOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = MagicMock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Mock district ingestion
            mock_orchestrator.ingest_districts.return_value = districts

            # Mock complaint ingestion to raise exception
            mock_orchestrator.ingest_complaints = AsyncMock(
                side_effect=Exception("Ingestion failed")
            )

            # Execute
            result = await run_ingestion_service(
                force_params=None,
                ingest_complaints=True,
                ingest_documents=False,
                ingest_action_history=False,
            )

            # Verify
            assert (
                result["statusCode"] == 200
            )  # Service should continue despite individual failures
            assert "Data ingestion completed successfully" in result["body"]

            # Verify logging was still properly managed
            mock_stop_logging.assert_called_once()
            mock_resume_logging.assert_called_once()
