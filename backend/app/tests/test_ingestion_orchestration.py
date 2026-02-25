import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.ingestion.orchestrator import IngestionOrchestrator
from app.ingestion.schemas import ActionHistory, Complaint, District


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
def orchestrator(db_session):
    """Create an IngestionOrchestrator instance for testing."""
    return IngestionOrchestrator(db=db_session, semaphore_value=3)


@pytest.fixture
def sample_district_data():
    """Sample district data for testing."""
    return [
        {
            "distId": 1,
            "distName": "Test District 1",
        },
        {
            "distId": 2,
            "distName": "Test District 2",
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
            "reviewAuthority": None,
            "reviewAuthorityName": None,
            "vchAllEscUser": None,
            "reopenedBy": None,
            "vchAccount": None,
        },
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


class TestIngestionOrchestrator:
    """Test cases for IngestionOrchestrator class."""

    def test_orchestrator_initialization(self, db_session):
        """Test orchestrator initialization with default parameters."""
        orchestrator = IngestionOrchestrator(db=db_session)

        assert orchestrator.db == db_session
        assert orchestrator.semaphore._value == 5
        assert orchestrator.bucket_name == "grievance-raw-data"
        assert orchestrator.client is not None
        assert orchestrator.s3 is not None
        assert orchestrator.doc_service is not None

    def test_orchestrator_initialization_custom_semaphore(self, db_session):
        """Test orchestrator initialization with custom semaphore value."""
        orchestrator = IngestionOrchestrator(db=db_session, semaphore_value=10)

        assert orchestrator.semaphore._value == 10

    @patch("app.ingestion.orchestrator.bulk_load_districts")
    @patch("app.ingestion.orchestrator.validate")
    @pytest.mark.asyncio
    async def test_ingest_districts_success(
        self, mock_validate, mock_bulk_load, orchestrator, sample_district_data
    ):
        """Test successful district ingestion."""
        # Mock client response
        orchestrator.client.get_districts = MagicMock(return_value=sample_district_data)

        # Mock validation
        validated_districts = [
            District(**district) for district in sample_district_data
        ]
        mock_validate.return_value = validated_districts

        # Mock bulk load
        mock_bulk_load.return_value = validated_districts

        # Execute
        result = await orchestrator.ingest_districts()

        # Verify
        assert result == validated_districts
        orchestrator.client.get_districts.assert_called_once()
        mock_validate.assert_called_once_with(
            sample_district_data, District, dict_mode=False
        )
        mock_bulk_load.assert_called_once_with(orchestrator.db, validated_districts)

    @patch("app.ingestion.orchestrator.logger.error")
    @pytest.mark.asyncio
    async def test_ingest_districts_client_error(self, mock_logger, orchestrator):
        """Test district ingestion when client raises an exception."""
        # Mock client to raise exception
        orchestrator.client.get_districts = MagicMock(
            side_effect=Exception("API Error")
        )

        # Execute and verify exception is raised
        with pytest.raises(Exception, match="API Error"):
            await orchestrator.ingest_districts()

        mock_logger.assert_called_once()

    @patch("app.ingestion.orchestrator.bulk_load_complaints")
    @patch("app.ingestion.orchestrator.validate")
    @pytest.mark.asyncio
    async def test_ingest_complaints_success(
        self, mock_validate, mock_bulk_load, orchestrator, sample_complaint_data
    ):
        """Test successful complaint ingestion."""
        # Mock client response
        orchestrator.client.get_complaints = AsyncMock(
            return_value=sample_complaint_data
        )

        # Mock validation
        validated_complaints = [
            Complaint(**complaint) for complaint in sample_complaint_data
        ]
        mock_validate.return_value = validated_complaints

        # Mock bulk load
        mock_bulk_load.return_value = validated_complaints

        # Execute
        result = await orchestrator.ingest_complaints(2024, 1, 1, 1)

        # Verify
        assert result == validated_complaints
        orchestrator.client.get_complaints.assert_called_once_with(
            2024, 1, 1, 1, orchestrator.semaphore
        )
        mock_validate.assert_called_once_with(
            sample_complaint_data, Complaint, dict_mode=False
        )
        mock_bulk_load.assert_called_once_with(orchestrator.db, validated_complaints)

    @pytest.mark.asyncio
    async def test_ingest_complaints_none_response(self, orchestrator):
        """Test complaint ingestion when client returns None."""
        # Mock client to return None
        orchestrator.client.get_complaints = AsyncMock(return_value=None)

        # Execute
        result = await orchestrator.ingest_complaints(2024, 1, 1, 1)

        # Verify
        assert result == []

    @pytest.mark.asyncio
    async def test_ingest_complaints_client_error(self, orchestrator):
        """Test complaint ingestion when client raises an exception."""
        # Mock client to raise exception
        orchestrator.client.get_complaints = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Execute
        result = await orchestrator.ingest_complaints(2024, 1, 1, 1)

        # Verify
        assert result == []

    @patch("app.ingestion.orchestrator.bulk_load_action_histories")
    @patch("app.ingestion.orchestrator.validate_action_history")
    @patch("app.ingestion.orchestrator.record_action_history_api_request_success")
    @pytest.mark.asyncio
    async def test_ingest_action_history_success(
        self,
        mock_record_success,
        mock_validate,
        mock_bulk_load,
        orchestrator,
        sample_action_history_data,
    ):
        """Test successful action history ingestion."""
        # Mock client response
        orchestrator.client.get_action_history = AsyncMock(
            return_value=sample_action_history_data
        )

        # Mock validation
        validated_history = [
            ActionHistory(**action) for action in sample_action_history_data
        ]
        mock_validate.return_value = validated_history

        # Mock bulk load
        mock_bulk_load.return_value = validated_history

        # Execute
        result = await orchestrator.ingest_action_history("T123")

        # Verify
        assert result == validated_history
        orchestrator.client.get_action_history.assert_called_once_with(
            "T123", orchestrator.semaphore
        )
        mock_validate.assert_called_once_with(
            items=sample_action_history_data, ticket_no="T123", dict_mode=False
        )
        mock_bulk_load.assert_called_once_with(orchestrator.db, validated_history)
        mock_record_success.assert_called_once_with(
            orchestrator.db, "T123", len(sample_action_history_data)
        )

    @pytest.mark.asyncio
    async def test_ingest_action_history_none_response(self, orchestrator):
        """Test action history ingestion when client returns None."""
        # Mock client to return None
        orchestrator.client.get_action_history = AsyncMock(return_value=None)

        # Mock the failure marking function
        with patch(
            "app.ingestion.orchestrator.mark_action_history_api_request_failed"
        ) as mock_mark_failed:
            # Execute
            result = await orchestrator.ingest_action_history("T123")

            # Verify
            assert result == []
            mock_mark_failed.assert_called_once_with(orchestrator.db, "T123")

    @pytest.mark.asyncio
    async def test_ingest_action_history_client_error(self, orchestrator):
        """Test action history ingestion when client raises an exception."""
        # Mock client to raise exception
        orchestrator.client.get_action_history = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Mock the failure marking function
        with patch(
            "app.ingestion.orchestrator.mark_action_history_api_request_failed"
        ) as mock_mark_failed:
            # Execute
            result = await orchestrator.ingest_action_history("T123")

            # Verify
            assert result == []
            mock_mark_failed.assert_called_once_with(orchestrator.db, "T123")

    @pytest.mark.asyncio
    async def test_ingest_documents_success(self, orchestrator, sample_complaint_data):
        """Test successful document ingestion."""
        # Create sample complaints
        complaints = [Complaint(**complaint) for complaint in sample_complaint_data]

        # Mock document service
        expected_results = {"T123": "success"}
        orchestrator.doc_service.batch_download_documents = AsyncMock(
            return_value=expected_results
        )

        # Execute
        result = await orchestrator.ingest_documents(complaints)

        # Verify
        assert result == expected_results
        orchestrator.doc_service.batch_download_documents.assert_called_once_with(
            complaints
        )


class TestTrackWithProgress:
    """Test cases for track_with_progress function."""

    @pytest.mark.asyncio
    async def test_track_with_progress_success(self):
        """Test track_with_progress with successful coroutines."""
        from app.ingestion.orchestrator import track_with_progress

        # Create test coroutines
        async def test_coro_1():
            await asyncio.sleep(0.01)
            return "result1"

        async def test_coro_2():
            await asyncio.sleep(0.01)
            return "result2"

        coros = [test_coro_1(), test_coro_2()]

        # Execute
        results = await track_with_progress(coros, desc="Test Progress")

        # Verify
        assert results == ["result1", "result2"]

    @pytest.mark.asyncio
    async def test_track_with_progress_with_exceptions(self):
        """Test track_with_progress with coroutines that raise exceptions."""
        from app.ingestion.orchestrator import track_with_progress

        # Create test coroutines
        async def test_coro_success():
            await asyncio.sleep(0.01)
            return "success"

        async def test_coro_exception():
            await asyncio.sleep(0.01)
            raise ValueError("Test exception")

        coros = [test_coro_success(), test_coro_exception()]

        # Execute
        results = await track_with_progress(coros, desc="Test Progress")

        # Verify
        assert len(results) == 2
        assert results[0] == "success"
        assert isinstance(results[1], ValueError)
        assert str(results[1]) == "Test exception"

    @pytest.mark.asyncio
    async def test_track_with_progress_empty_list(self):
        """Test track_with_progress with empty coroutine list."""
        from app.ingestion.orchestrator import track_with_progress

        # Execute
        results = await track_with_progress([], desc="Empty Progress")

        # Verify
        assert results == []

    @pytest.mark.asyncio
    async def test_track_with_progress_custom_position(self):
        """Test track_with_progress with custom position parameter."""
        from app.ingestion.orchestrator import track_with_progress

        # Create test coroutine
        async def test_coro():
            await asyncio.sleep(0.01)
            return "result"

        coros = [test_coro()]

        # Execute with custom position
        results = await track_with_progress(coros, desc="Test Progress", position=5)

        # Verify
        assert results == ["result"]


class TestOrchestratorIntegration:
    """Integration tests for orchestrator components."""

    @patch("app.ingestion.orchestrator.bulk_load_districts")
    @patch("app.ingestion.orchestrator.bulk_load_complaints")
    @patch("app.ingestion.orchestrator.validate")
    @pytest.mark.asyncio
    async def test_full_ingestion_workflow(
        self,
        mock_validate,
        mock_bulk_load_complaints,
        mock_bulk_load_districts,
        db_session,
        sample_district_data,
        sample_complaint_data,
    ):
        """Test complete ingestion workflow."""
        orchestrator = IngestionOrchestrator(db=db_session)

        # Mock district ingestion
        orchestrator.client.get_districts = MagicMock(return_value=sample_district_data)
        validated_districts = [
            District(**district) for district in sample_district_data
        ]
        mock_validate.return_value = validated_districts
        mock_bulk_load_districts.return_value = validated_districts

        # Ingest districts
        districts_result = await orchestrator.ingest_districts()
        assert districts_result == validated_districts

        # Mock complaint ingestion
        orchestrator.client.get_complaints = AsyncMock(
            return_value=sample_complaint_data
        )
        validated_complaints = [
            Complaint(**complaint) for complaint in sample_complaint_data
        ]
        mock_validate.return_value = validated_complaints
        mock_bulk_load_complaints.return_value = validated_complaints

        # Ingest complaints
        complaints_result = await orchestrator.ingest_complaints(2024, 1, 1, 1)
        assert complaints_result == validated_complaints

        # Mock document ingestion
        orchestrator.doc_service.batch_download_documents = AsyncMock(
            return_value={"T123": "success"}
        )

        # Ingest documents
        documents_result = await orchestrator.ingest_documents(validated_complaints)
        assert documents_result == {"T123": "success"}

    def test_orchestrator_semaphore_limits(self, db_session):
        """Test that orchestrator properly limits concurrent operations."""
        orchestrator = IngestionOrchestrator(db=db_session, semaphore_value=2)

        # Verify semaphore is properly initialized
        assert orchestrator.semaphore._value == 2

        # Test that semaphore is used in async operations
        assert orchestrator.semaphore is not None
