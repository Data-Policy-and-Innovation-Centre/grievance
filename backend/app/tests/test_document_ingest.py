import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.crud import get_complaint_by_ticket
from app.db.models import Base
from app.db.models import Complaint as ComplaintModel
from app.ingestion.document_ingestion import DocumentService
from app.ingestion.schemas import Complaint as ComplaintSchema


# Test database setup
@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a fresh database for each test."""
    # Create in-memory SQLite database for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create a new session for the test
    TestingAsyncSessionLocal = sessionmaker(bind = engine, class_=AsyncSession, expire_on_commit=False)

    async with TestingAsyncSessionLocal() as session:
        yield session 


@pytest_asyncio.fixture(scope="function")
async def sample_complaint_data(db_session):
    complaint = ComplaintModel(
        ticket_no="T123",
        petitioner_name="John Doe",
        petitioner_mobile="1234567890",
        petitioner_email="john@example.com",
        grievance="Test Grievance",
        document_url="www.example~pdf",
        office="Cheif Minister",
        received_by="Officer X",
        district="Test District",
        block="Test Block",
        address="123 Test St",
        mode="Online",
        disability=None,
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 3, 20, 10, 0),
        assigned_on=datetime(2024, 3, 20, 10, 0),
        category="Test Category",
        dept="Test Dept",
        subcategory="Test Subcategory",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
    )
    db_session.add(complaint)
    await db_session.commit()
    return complaint


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


@pytest.fixture
def doc_service(db_session):
    return DocumentService(db=db_session)


@pytest.fixture(autouse=True)
def mock_aws_settings(monkeypatch):
    """Mock AWS settings to prevent S3 validation errors in tests."""
    monkeypatch.setattr("app.config.settings.AWS_S3_DOCUMENTS", "test-bucket-name")
    monkeypatch.setattr("app.config.settings.AWS_S3_BUCKET_NAME", "test-bucket-name")


# Test
@pytest.mark.asyncio
async def test_get_document_path(doc_service, sample_complaint_data):
    fixed_now = datetime(2025, 7, 1, 15, 15, 0)

    with patch("app.ingestion.document_ingestion.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        mock_datetime.strftime = datetime.strftime  # opcional, por seguridad
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        doc_path = await doc_service.get_document_path(
            sample_complaint_data.ticket_no, "complaint"
        )

        expected_name = f"T123_complaint_{fixed_now.strftime('%Y%m%d_%H%M%S')}.pdf"

        assert doc_path.endswith(expected_name)


@pytest.mark.asyncio
async def test_get_document_path_ticket_no(doc_service):
    assert await doc_service.get_document_path("NO_TICKET", "compliant") is None


@pytest.mark.parametrize("environment", ["dev", "main"])
@pytest.mark.asyncio
async def test_document_exists_returns_true(db_session, tmp_path, monkeypatch, environment):
    from app.config import settings

    if environment == "dev":
        # For dev environment, create the file in the local storage path
        storage_path = tmp_path / environment
        storage_path.mkdir(exist_ok=True)
        file_name = "T123_complaint_20240702_123456.pdf"
        file_path = storage_path / file_name
        file_path.write_text("test")
        monkeypatch.setattr(settings, "ENV", environment)
        monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(storage_path))
        from app.ingestion.document_ingestion import DocumentService

        doc_service = DocumentService(db=db_session)
        with patch.object(
            doc_service, "get_document_path", return_value=str(file_path)
        ):
            assert (
                doc_service.document_already_downloaded("T123", "complaint", "pdf")
                is True
            )
    else:
        monkeypatch.setattr(settings, "ENV", environment)
        from app.ingestion.document_ingestion import DocumentService

        doc_service = DocumentService(db=db_session)
        with patch.object(
            doc_service, "_document_already_downloaded_s3", return_value=True
        ):
            assert (
                doc_service.document_already_downloaded("T123", "complaint", "pdf")
                is True
            )


@pytest.mark.asyncio
async def test_document_exists_returns_false(doc_service, tmp_path, monkeypatch):
    file_path = tmp_path / "T123_complaint_20240702_123456.pdf"

    monkeypatch.setattr(
        "app.ingestion.document_ingestion.settings.LOCAL_STORAGE_PATH", str(tmp_path)
    )

    with patch.object(
        doc_service, "get_document_path", return_value=str(file_path)
    ), patch("os.path.exists", return_value=False), patch.object(
        doc_service, "_document_already_downloaded_s3", return_value=False
    ):
        assert (
            doc_service.document_already_downloaded("T123", "complaint", "pdf") is False
        )


@pytest.mark.parametrize("environment", ["dev", "main"])
@pytest.mark.asyncio
async def test_download_document_success(
    db_session, tmp_path, monkeypatch, environment
):
    from app.config import settings

    # Set environment before creating service
    monkeypatch.setattr(settings, "ENV", environment)

    # Create a proper test path that matches what the service will generate
    expected_filename = "T123_complaint_20250101_120000.pdf"
    test_path = tmp_path / expected_filename

    # Create complaint with proper document URL format and add to database
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="http://example.com/file~pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint)
    await db_session.commit()

    # Create DocumentService after patching environment
    from app.ingestion.document_ingestion import DocumentService

    doc_service = DocumentService(db=db_session)

    if environment == "dev":
        # For dev environment, mock local file operations
        mock_file = AsyncMock()
        mock_open_ctx = AsyncMock()
        mock_open_ctx.__aenter__.return_value = mock_file

        with patch.object(
            doc_service, "get_document_path", return_value=str(test_path)
        ), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, patch(
            "aiofiles.open", return_value=mock_open_ctx
        ), patch.object(
            doc_service, "document_already_downloaded", return_value=False
        ):

            # Mock httpx response
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = b"PDF_CONTENT"
            mock_get.return_value.raise_for_status = MagicMock()

            path = await doc_service.download_document(complaint, "complaint")

            assert path == str(test_path)
            mock_file.write.assert_called_once_with(b"PDF_CONTENT")
    else:
        # For main environment, mock S3 operations
        with patch.object(
            doc_service, "get_document_path", return_value=str(test_path)
        ), patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock
        ) as mock_get, patch.object(
            doc_service.s3_service, "upload_fileobj"
        ) as mock_upload, patch.object(
            doc_service, "document_already_downloaded", return_value=False
        ):

            # Mock httpx response
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = b"PDF_CONTENT"
            mock_get.return_value.raise_for_status = MagicMock()

            path = await doc_service.download_document(complaint, "complaint")

            assert path == str(test_path)
            mock_upload.assert_called_once_with(b"PDF_CONTENT", str(test_path))


@pytest.mark.asyncio
async def test_download_document_invalid_url(doc_service, tmp_path, db_session):
    test_path = tmp_path / "file.pdf"
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="example.com/file~pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint)
    await db_session.commit()

    with patch.object(
        doc_service, "get_document_path", return_value=str(test_path)
    ), patch.object(
        doc_service, "document_already_downloaded", return_value=False
    ), patch(
        "httpx.AsyncClient.get", side_effect=Exception("Simulated error")
    ), patch(
        "app.ingestion.document_ingestion.update_document_status"
    ) as mock_update_status, patch(
        "app.ingestion.document_ingestion.logger.error"
    ) as mock_log_error:

        result = await doc_service.download_document(complaint, "complaint")

        assert result is None


@pytest.mark.asyncio
async def test_download_document_no_path_logs(doc_service):
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="https://www.example.com/file~pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )

    with patch.object(doc_service, "get_document_path", return_value=None), patch(
        "app.ingestion.document_ingestion.logger.warning"
    ) as mock_log:

        result = await doc_service.download_document(complaint, "complaint")

        # Assert it returned None
        assert result is None

        # Assert the warning log was called
        mock_log.assert_any_call("Failed to generate a path for complaint T123")


@pytest.mark.asyncio
async def test_download_document_error(doc_service, tmp_path, caplog, db_session):
    test_path = tmp_path / "file.pdf"
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="http://example.com/file~pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint)
    await db_session.commit()

    with patch.object(
        doc_service, "get_document_path", return_value=str(test_path)
    ), patch.object(
        doc_service, "document_already_downloaded", return_value=False
    ), patch(
        "httpx.AsyncClient.get", side_effect=Exception("Simulated error")
    ), patch(
        "app.ingestion.document_ingestion.logger.error"
    ) as mock_log_error:

        result = await doc_service.download_document(complaint, "complaint")

        assert result is None

        mock_log_error.assert_any_call(
            "Error downloading document for T123: Simulated error"
        )


@pytest.mark.asyncio
async def test_batch_download_documents_success(doc_service, db_session):
    doc_service

    # Mock complaint
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="http://example.com/file~pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint)
    await db_session.commit()

    # Mock db context manager
    mock_db = MagicMock()
    doc_service.db = mock_db
    mock_db_context = AsyncMock()
    mock_db_context.__aenter__.return_value = mock_db

    # Mock download and update
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download:

        mock_download.return_value = "/mocked/path/file.pdf"

        results = await doc_service.batch_download_documents([complaint])

        assert results == {"T123": "success"}
        mock_download.assert_called_once_with(complaint)


@pytest.mark.asyncio
async def test_batch_download_documents_handles_exception(doc_service, db_session):
    complaint1 = ComplaintModel(
        ticket_no="T999",
        document_url="https://example.com/file.pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    complaint2 = ComplaintModel(
        ticket_no="T989",
        document_url="https://example.com/file.pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint1)
    db_session.add(complaint2)
    await db_session.commit()

    doc_service.db = db_session

    doc_service.download_document = AsyncMock(side_effect=Exception("Boom!"))
    fake_updated_complaint = MagicMock()
    fake_updated_complaint.ticket_no = "T999"

    with patch(
        "app.ingestion.document_ingestion.update_document_status", return_value=None
    ):
        result = await doc_service.batch_download_documents([complaint1, complaint2])
        assert result == {"T989": "failed", "T999": "failed"}


def test_document_service_uses_env_setting(db_session, monkeypatch):
    """Test that DocumentService uses settings.ENV for local folder creation."""
    # Mock settings.ENV to be "local"
    monkeypatch.setattr("app.ingestion.document_ingestion.settings.ENV", "dev")

    # Mock os.mkdir to verify it's called
    with patch("os.mkdir") as mock_mkdir, patch("os.path.exists", return_value=False):
        doc_service = DocumentService(db=db_session)
        mock_mkdir.assert_called_once()


def test_document_service_skips_local_folder_when_not_local(db_session, monkeypatch):
    """Test that DocumentService skips local folder creation when ENV is not 'local'."""
    # Mock settings.ENV to be "prod"
    monkeypatch.setattr("app.ingestion.document_ingestion.settings.ENV", "prod")

    # Mock os.mkdir to verify it's NOT called
    with patch("os.mkdir") as mock_mkdir:
        doc_service = DocumentService(db=db_session)
        mock_mkdir.assert_not_called()


# Updated and new tests for batch_download_documents
@pytest.mark.asyncio
async def test_batch_download_documents_success(doc_service, db_session):
    """Test batch_download_documents with the new bulk update implementation."""
    # Create test complaints
    complaints = []
    for i in range(3):
        complaint = ComplaintModel(
            ticket_no=f"T{i+1}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Mock download_document to return success paths
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download, patch.object(
        doc_service, "_bulk_update_document_status", new_callable=AsyncMock
    ) as mock_bulk_update:

        # Mock successful downloads
        mock_download.side_effect = [
            "/path/to/doc1.pdf",
            "/path/to/doc2.pdf",
            "/path/to/doc3.pdf",
        ]

        results = await doc_service.batch_download_documents(complaints)

        # Verify results
        assert results == {"T1": "success", "T2": "success", "T3": "success"}

        # Verify download_document was called for each complaint
        assert mock_download.call_count == 3
        mock_download.assert_any_call(complaints[0])
        mock_download.assert_any_call(complaints[1])
        mock_download.assert_any_call(complaints[2])

        # Verify bulk update was called with correct data
        assert mock_bulk_update.call_count == 1
        call_args = mock_bulk_update.call_args[0][0]
        assert len(call_args) == 3

        # Check the update data structure
        for update_data in call_args:
            assert "ticket_no" in update_data
            assert "local_path" in update_data
            assert "success" in update_data
            assert "error" in update_data
            assert update_data["success"] is True
            assert update_data["error"] is None


@pytest.mark.asyncio
async def test_batch_download_documents_mixed_success_failure(doc_service, db_session):
    """Test batch_download_documents with mixed success and failure scenarios."""
    # Create test complaints
    complaints = []
    for i in range(4):
        complaint = ComplaintModel(
            ticket_no=f"T{i+1}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Mock download_document with mixed results
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download, patch.object(
        doc_service, "_bulk_update_document_status", new_callable=AsyncMock
    ) as mock_bulk_update:

        # Create a deterministic mock that returns based on ticket_no
        def mock_download_side_effect(complaint):
            if complaint.ticket_no == "T1":
                return "/path/to/doc1.pdf"  # Success
            elif complaint.ticket_no == "T2":
                raise Exception("Download failed")  # Failure
            elif complaint.ticket_no == "T3":
                return "/path/to/doc3.pdf"  # Success
            elif complaint.ticket_no == "T4":
                raise Exception("Network error")  # Failure
            else:
                return None

        mock_download.side_effect = mock_download_side_effect

        results = await doc_service.batch_download_documents(complaints)

        # Verify results (order-independent)
        expected_results = {
            "T1": "success",
            "T2": "failed",
            "T3": "success",
            "T4": "failed",
        }
        assert results == expected_results

        # Verify bulk update was called with correct data
        assert mock_bulk_update.call_count == 1
        call_args = mock_bulk_update.call_args[0][0]
        assert len(call_args) == 4

        # Check success cases (order-independent)
        success_updates = [u for u in call_args if u["success"]]
        assert len(success_updates) == 2
        success_tickets = {u["ticket_no"] for u in success_updates}
        assert success_tickets == {"T1", "T3"}

        # Check failure cases (order-independent)
        failure_updates = [u for u in call_args if not u["success"]]
        assert len(failure_updates) == 2
        failure_tickets = {u["ticket_no"] for u in failure_updates}
        assert failure_tickets == {"T2", "T4"}

        # Verify specific error messages
        for update in call_args:
            if update["ticket_no"] == "T2":
                assert "Download failed" in update["error"]
            elif update["ticket_no"] == "T4":
                assert "Network error" in update["error"]


@pytest.mark.asyncio
async def test_batch_download_documents_batch_commits(doc_service, db_session):
    """Test that batch_download_documents commits in batches of 500."""
    # Create 600 test complaints to test batch processing
    complaints = []
    for i in range(600):
        complaint = ComplaintModel(
            ticket_no=f"T{i+1:03d}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Mock download_document to return success
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download, patch.object(
        doc_service, "_bulk_update_document_status", new_callable=AsyncMock
    ) as mock_bulk_update:

        # Mock successful downloads
        mock_download.return_value = "/path/to/doc.pdf"

        results = await doc_service.batch_download_documents(complaints)

        # Verify all results are success
        assert len(results) == 600
        assert all(status == "success" for status in results.values())

        # Verify bulk update was called twice (500 + 100)
        assert mock_bulk_update.call_count == 2

        # Check first batch (500 items)
        first_batch = mock_bulk_update.call_args_list[0][0][0]
        assert len(first_batch) == 500

        # Check second batch (100 items)
        second_batch = mock_bulk_update.call_args_list[1][0][0]
        assert len(second_batch) == 100


@pytest.mark.asyncio
async def test_batch_download_documents_empty_list(doc_service):
    """Test batch_download_documents with empty complaint list."""
    with patch.object(
        doc_service, "_bulk_update_document_status", new_callable=AsyncMock
    ) as mock_bulk_update:

        results = await doc_service.batch_download_documents([])

        assert results == {}
        mock_bulk_update.assert_not_called()


@pytest.mark.asyncio
async def test_batch_download_documents_skipped_documents(doc_service, db_session):
    """Test batch_download_documents when documents are already downloaded."""
    # Create test complaint
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="http://example.com/file.pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint)
    await db_session.commit()

    # Mock download_document to return None (already downloaded)
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download, patch.object(
        doc_service, "_bulk_update_document_status", new_callable=AsyncMock
    ) as mock_bulk_update:

        mock_download.return_value = None  # Document already downloaded

        results = await doc_service.batch_download_documents([complaint])

        assert results == {"T123": "skipped"}

        # Verify bulk update was called with skipped data
        mock_bulk_update.assert_called_once()
        call_args = mock_bulk_update.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["ticket_no"] == "T123"
        assert call_args[0]["local_path"] is None
        assert call_args[0]["success"] is False
        assert call_args[0]["error"] is None


# Tests for _bulk_update_document_status
@pytest.mark.asyncio
async def test_bulk_update_document_status_success(doc_service, db_session):
    """Test successful bulk update of document status."""
    # Create test complaints
    complaints = []
    for i in range(3):
        complaint = ComplaintModel(
            ticket_no=f"T{i+1}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Prepare update data
    updates = [
        {
            "ticket_no": "T1",
            "local_path": "/path/to/doc1.pdf",
            "success": True,
            "error": None,
        },
        {
            "ticket_no": "T2",
            "local_path": None,
            "success": False,
            "error": "Download failed",
        },
        {
            "ticket_no": "T3",
            "local_path": "/path/to/doc3.pdf",
            "success": True,
            "error": None,
        },
    ]

    # Mock the database execute and commit
    with patch.object(doc_service.db, "execute") as mock_execute, patch.object(
        doc_service.db, "commit"
    ) as mock_commit, patch.object(doc_service.db, "rollback") as mock_rollback, patch(
        "app.ingestion.document_ingestion.logger.info"
    ) as mock_logger:

        # Mock the result object
        mock_result = AsyncMock()
        mock_result.rowcount = 3
        mock_execute.return_value = mock_result

        await doc_service._bulk_update_document_status(updates)

        # Verify execute was called
        mock_execute.assert_called_once()

        # Verify commit was called
        mock_commit.assert_called_once()

        # Verify rollback was not called
        mock_rollback.assert_not_called()

        # Verify logging
        mock_logger.assert_called_with("Bulk updated 3 document statuses")


@pytest.mark.asyncio
async def test_bulk_update_document_status_database_error(doc_service, db_session):
    """Test bulk update when database operation fails."""
    updates = [
        {
            "ticket_no": "T1",
            "local_path": "/path/to/doc1.pdf",
            "success": True,
            "error": None,
        }
    ]

    # Mock database error
    with patch.object(
        doc_service.db, "execute", side_effect=Exception("Database error")
    ), patch.object(doc_service.db, "commit") as mock_commit, patch.object(
        doc_service.db, "rollback"
    ) as mock_rollback, patch(
        "app.ingestion.document_ingestion.logger.error"
    ) as mock_logger:

        with pytest.raises(Exception, match="Database error"):
            await doc_service._bulk_update_document_status(updates)

        # Verify rollback was called
        mock_rollback.assert_called_once()

        # Verify commit was not called
        mock_commit.assert_not_called()

        # Verify error logging
        mock_logger.assert_called_with(
            "Error in bulk document status update: Database error"
        )


@pytest.mark.asyncio
async def test_bulk_update_document_status_empty_updates(doc_service):
    """Test bulk update with empty updates list."""
    with patch.object(doc_service.db, "execute") as mock_execute, patch.object(
        doc_service.db, "commit"
    ) as mock_commit, patch(
        "app.ingestion.document_ingestion.logger.info"
    ) as mock_logger:

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_execute.return_value = mock_result

        await doc_service._bulk_update_document_status([])

        # Verify execute was called (even with empty list)
        mock_execute.assert_called_once()

        # Verify commit was called
        mock_commit.assert_called_once()

        # Verify logging
        mock_logger.assert_called_with("Bulk updated 0 document statuses")


@pytest.mark.asyncio
async def test_bulk_update_document_status_large_batch(doc_service, db_session):
    """Test bulk update with a large batch of updates."""
    # Create 100 test complaints
    complaints = []
    for i in range(100):
        complaint = ComplaintModel(
            ticket_no=f"T{i+1:03d}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Prepare large update data
    updates = []
    for i in range(100):
        updates.append(
            {
                "ticket_no": f"T{i+1:03d}",
                "local_path": f"/path/to/doc{i+1:03d}.pdf",
                "success": i % 2 == 0,  # Alternate success/failure
                "error": f"Error {i}" if i % 2 == 1 else None,
            }
        )

    with patch.object(doc_service.db, "execute") as mock_execute, patch.object(
        doc_service.db, "commit"
    ) as mock_commit, patch(
        "app.ingestion.document_ingestion.logger.info"
    ) as mock_logger:

        mock_result = MagicMock()
        mock_result.rowcount = 100
        mock_execute.return_value = mock_result

        await doc_service._bulk_update_document_status(updates)

        # Verify execute was called
        mock_execute.assert_called_once()

        # Verify commit was called
        mock_commit.assert_called_once()

        # Verify logging
        mock_logger.assert_called_with("Bulk updated 100 document statuses")


@pytest.mark.asyncio
async def test_bulk_update_document_status_verifies_database_changes(
    doc_service, db_session
):
    """Test that bulk update actually changes the database."""
    # Create test complaint
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="http://example.com/file.pdf",
        grievance="Test grievance",
        office="Test Office",
        received_by="Test Officer",
        district="Test District",
        mode="Online",
        status="Pending",
        govt_ticket=True,
        created_on=datetime(2024, 1, 1, 12, 0),
        category="Test Category",
        state="Test State",
        petitioner_gender="Male",
        transfer_status="None",
        urgent="No",
        assigned_on=datetime(2024, 1, 1, 12, 0),
    )
    db_session.add(complaint)
    await db_session.commit()

    # Verify initial state
    assert complaint.local_document_path is None
    assert complaint.document_downloaded is False
    assert complaint.document_download_error is None

    # Prepare update data
    updates = [
        {
            "ticket_no": "T123",
            "local_path": "/path/to/updated.pdf",
            "success": True,
            "error": None,
        }
    ]

    # Perform bulk update
    await doc_service._bulk_update_document_status(updates)

    # Refresh the complaint from database
    await db_session.refresh(complaint)

    # Verify the changes were applied
    assert complaint.local_document_path == "/path/to/updated.pdf"
    assert complaint.document_downloaded is True
    assert complaint.document_download_error is None
    assert complaint.document_download_date is not None


# Integration tests
@pytest.mark.asyncio
async def test_batch_download_documents_integration_with_bulk_update(
    doc_service, db_session
):
    """Test integration between batch_download_documents and _bulk_update_document_status."""
    # Create test complaints
    complaints = []
    for i in range(5):
        complaint = ComplaintModel(
            ticket_no=f"T{i+1}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Mock download_document with mixed results
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download:

        def mock_download_side_effect(complaint):
            if complaint.ticket_no == "T1":
                return "/path/to/doc1.pdf"
            elif complaint.ticket_no == "T2":
                raise Exception("Download failed")
            elif complaint.ticket_no == "T3":
                return "/path/to/doc3.pdf"
            elif complaint.ticket_no == "T4":
                return None
            elif complaint.ticket_no == "T5":
                raise Exception("Network error")
            else:
                return None

        mock_download.side_effect = mock_download_side_effect

        # Mock the bulk update to capture what it receives
        bulk_updates_received = []

        async def mock_bulk_update(updates):
            bulk_updates_received.extend(updates)

        doc_service._bulk_update_document_status = mock_bulk_update

        results = await doc_service.batch_download_documents(complaints)

        # Verify results
        assert results == {
            "T1": "success",
            "T2": "failed",
            "T3": "success",
            "T4": "skipped",
            "T5": "failed",
        }

        # Verify bulk updates were captured correctly
        assert len(bulk_updates_received) == 5

        # Check success case
        success_update = next(
            u for u in bulk_updates_received if u["ticket_no"] == "T1"
        )
        assert success_update["local_path"] == "/path/to/doc1.pdf"
        assert success_update["success"] is True
        assert success_update["error"] is None

        # Check failure case
        failure_update = next(
            u for u in bulk_updates_received if u["ticket_no"] == "T2"
        )
        assert failure_update["local_path"] is None
        assert failure_update["success"] is False
        assert "Download failed" in failure_update["error"]

        # Check skipped case
        skipped_update = next(
            u for u in bulk_updates_received if u["ticket_no"] == "T4"
        )
        assert skipped_update["local_path"] is None
        assert skipped_update["success"] is False
        assert skipped_update["error"] is None


@pytest.mark.asyncio
async def test_batch_download_documents_in_chunks(doc_service, db_session):
    """Test batch_download_documents_in_chunks functionality."""
    # Create test complaints
    complaints = []
    for i in range(250):  # More than chunk size
        complaint = ComplaintModel(
            ticket_no=f"T{i+1:03d}",
            document_url="http://example.com/file.pdf",
            grievance="Test grievance",
            office="Test Office",
            received_by="Test Officer",
            district="Test District",
            mode="Online",
            status="Pending",
            govt_ticket=True,
            created_on=datetime(2024, 1, 1, 12, 0),
            category="Test Category",
            state="Test State",
            petitioner_gender="Male",
            transfer_status="None",
            urgent="No",
            assigned_on=datetime(2024, 1, 1, 12, 0),
        )
        complaints.append(complaint)
        db_session.add(complaint)
    await db_session.commit()

    # Mock batch_download_documents
    with patch.object(
        doc_service, "batch_download_documents", new_callable=AsyncMock
    ) as mock_batch_download, patch(
        "app.ingestion.document_ingestion.logger.info"
    ) as mock_logger, patch(
        "app.ingestion.document_ingestion.logger.success"
    ) as mock_success_logger:

        # Mock results for each chunk
        mock_batch_download.side_effect = [
            {f"T{i+1:03d}": "success" for i in range(100)},  # First chunk
            {f"T{i+1:03d}": "success" for i in range(100, 200)},  # Second chunk
            {f"T{i+1:03d}": "success" for i in range(200, 250)},  # Third chunk
        ]

        results = await doc_service.batch_download_documents_in_chunks(
            complaints, chunk_size=100
        )

        # Verify batch_download_documents was called 3 times
        assert mock_batch_download.call_count == 3

        # Verify logging
        assert mock_logger.call_count == 3  # One for each chunk
        assert mock_success_logger.call_count == 3  # One for each chunk completion

        # Verify final results
        assert len(results) == 250
        assert all(status == "success" for status in results.values())
