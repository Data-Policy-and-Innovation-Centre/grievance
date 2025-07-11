import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.models import Complaint as ComplaintModel
from app.ingestion.document_ingestion import DocumentService
from app.ingestion.schemas import Complaint as ComplaintSchema


# Test database setup
@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    # Create in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    # Create a new session for the test
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def sample_complaint_data(db_session):
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
    db_session.commit()
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
def test_get_document_path(doc_service, sample_complaint_data):
    fixed_now = datetime(2025, 7, 1, 15, 15, 0)

    with patch("app.ingestion.document_ingestion.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        mock_datetime.strftime = datetime.strftime  # opcional, por seguridad
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        doc_path = doc_service.get_document_path(
            sample_complaint_data.ticket_no, "complaint"
        )

        expected_name = f"T123_complaint_{fixed_now.strftime('%Y%m%d_%H%M%S')}.pdf"

        assert doc_path.endswith(expected_name)


def test_get_document_path_ticket_no(doc_service):
    assert doc_service.get_document_path("NO_TICKET", "compliant") is None


@pytest.mark.parametrize("environment", ["dev", "main"])
def test_document_exists_returns_true(db_session, tmp_path, monkeypatch, environment):
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


def test_document_exists_returns_false(doc_service, tmp_path, monkeypatch):
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
        grievance="Test grievance",  # Required field
        office="Test Office",  # Required field
        received_by="Test Officer",  # Required field
        district="Test District",  # Required field
        mode="Online",  # Required field
        status="Pending",  # Required field
        govt_ticket=True,  # Required field
        created_on=datetime(2024, 1, 1, 12, 0),  # Required field
        category="Test Category",  # Required field
        state="Test State",  # Required field
        petitioner_gender="Male",  # Required field
        transfer_status="None",  # Required field
        urgent="No",  # Required field
        assigned_on=datetime(2024, 1, 1, 12, 0),  # Required field
    )
    db_session.add(complaint)
    db_session.commit()

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
async def test_download_document_error_updates_db(
    doc_service, tmp_path, caplog, db_session
):
    test_path = tmp_path / "file.pdf"
    complaint = ComplaintModel(
        ticket_no="T123",
        document_url="http://example.com/file~pdf",
        grievance="Test grievance",  # Required field
        office="Test Office",  # Required field
        received_by="Test Officer",  # Required field
        district="Test District",  # Required field
        mode="Online",  # Required field
        status="Pending",  # Required field
        govt_ticket=True,  # Required field
        created_on=datetime(2024, 1, 1, 12, 0),  # Required field
        category="Test Category",  # Required field
        state="Test State",  # Required field
        petitioner_gender="Male",  # Required field
        transfer_status="None",  # Required field
        urgent="No",  # Required field
        assigned_on=datetime(2024, 1, 1, 12, 0),  # Required field
    )
    db_session.add(complaint)
    db_session.commit()

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

        assert result == "Error"
        mock_update_status.assert_called_once_with(
            doc_service.db,
            "T123",
            local_path="",
            success=False,
            error="Error: Simulated error",
        )
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
        grievance="Test grievance",  # Required field
        office="Test Office",  # Required field
        received_by="Test Officer",  # Required field
        district="Test District",  # Required field
        mode="Online",  # Required field
        status="Pending",  # Required field
        govt_ticket=True,  # Required field
        created_on=datetime(2024, 1, 1, 12, 0),  # Required field
        category="Test Category",  # Required field
        state="Test State",  # Required field
        petitioner_gender="Male",  # Required field
        transfer_status="None",  # Required field
        urgent="No",  # Required field
        assigned_on=datetime(2024, 1, 1, 12, 0),  # Required field
    )
    db_session.add(complaint)
    db_session.commit()

    # Mock db context manager
    mock_db = MagicMock()
    doc_service.db = mock_db
    mock_db_context = AsyncMock()
    mock_db_context.__aenter__.return_value = mock_db

    # Mock download and update
    with patch.object(
        doc_service, "download_document", new_callable=AsyncMock
    ) as mock_download, patch(
        "app.ingestion.document_ingestion.update_document_status"
    ) as mock_update:

        mock_download.return_value = "/mocked/path/file.pdf"

        results = await doc_service.batch_download_documents([complaint])

        assert results == {"T123": "success"}
        mock_download.assert_called_once_with(complaint)
        mock_update.assert_called_once_with(
            mock_db, "T123", local_path="/mocked/path/file.pdf", success=True
        )


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
