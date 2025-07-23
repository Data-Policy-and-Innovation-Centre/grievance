import io
import os
from unittest.mock import MagicMock, Mock, mock_open, patch

import boto3
import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from moto import mock_aws

from app.config import settings
from app.s3service import S3Service


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def mock_s3_client(aws_credentials):
    """Mock S3 client for testing."""
    with mock_aws():
        s3_client = boto3.client("s3")
        # Create the test bucket
        s3_client.create_bucket(Bucket="test-bucket")
        yield s3_client


@pytest.fixture(scope="function")
def mock_s3_resource(aws_credentials):
    """Mock S3 resource for testing."""
    with mock_aws():
        s3_resource = boto3.resource("s3")
        # Create the test bucket
        s3_resource.create_bucket(Bucket="test-bucket")
        yield s3_resource


@pytest.fixture
def s3_service(mock_s3_client, mock_s3_resource):
    """Create an S3Service instance for testing."""
    return S3Service(
        bucket_name="test-bucket",
        s3_client=mock_s3_client,
        s3_resource=mock_s3_resource,
    )


class TestS3Service:
    """Test cases for S3Service class."""

    def test_init_with_custom_bucket(self):
        """Test S3Service initialization with custom bucket name."""
        service = S3Service(bucket_name="custom-bucket")
        assert service.bucket_name == "custom-bucket"

    def test_init_with_default_bucket(self):
        """Test S3Service initialization with default bucket name."""
        with patch("app.s3service.settings.AWS_S3_DOCUMENTS", "default-bucket"):
            service = S3Service()
            assert service.bucket_name == "default-bucket"

    def test_upload_file_success(self, s3_service, tmp_path):
        """Test successful file upload to S3."""
        # Create a temporary file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        result = s3_service.upload_file(
            file_path=str(test_file),
            s3_key="documents/test.pdf",
            content_type="application/pdf",
        )

        assert result is True

    def test_upload_file_without_content_type(self, s3_service, tmp_path):
        """Test file upload without content type."""
        # Create a temporary file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        result = s3_service.upload_file(
            file_path=str(test_file), s3_key="documents/test.pdf"
        )

        assert result is True

    def test_upload_file_client_error(self, s3_service, mock_s3_client, tmp_path):
        """Test file upload with ClientError."""
        # Create a temporary file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        with patch.object(
            mock_s3_client,
            "upload_file",
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "Bucket does not exist"}},
                "upload_file",
            ),
        ):
            result = s3_service.upload_file(
                file_path=str(test_file), s3_key="documents/test.pdf"
            )

            assert result is False

    def test_upload_file_no_credentials(self, s3_service, mock_s3_client, tmp_path):
        """Test file upload with NoCredentialsError."""
        # Create a temporary file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        with patch.object(
            mock_s3_client, "upload_file", side_effect=NoCredentialsError()
        ):
            result = s3_service.upload_file(
                file_path=str(test_file), s3_key="documents/test.pdf"
            )

            assert result is False

    def test_upload_fileobj_success(self, s3_service, mock_s3_client):
        """Test successful file object upload to S3."""
        file_obj = io.BytesIO(b"test content")

        result = s3_service.upload_fileobj(
            file_obj=file_obj, s3_key="documents/test.txt", content_type="text/plain"
        )

        assert result is True

    def test_upload_fileobj_client_error(self, s3_service, mock_s3_client):
        """Test file object upload with ClientError."""
        with patch.object(
            mock_s3_client,
            "upload_fileobj",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                "upload_fileobj",
            ),
        ):
            file_obj = io.BytesIO(b"test content")
            result = s3_service.upload_fileobj(
                file_obj=file_obj, s3_key="documents/test.txt"
            )

            assert result is False

    def test_download_file_success(self, s3_service, mock_s3_client, tmp_path):
        """Test successful file download from S3."""
        # First upload a file to S3
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")
        s3_service.upload_file(str(test_file), "documents/test.pdf")

        # Now download it
        download_path = tmp_path / "downloaded.pdf"
        with patch("os.makedirs") as mock_makedirs:
            result = s3_service.download_file(
                s3_key="documents/test.pdf", local_path=str(download_path)
            )

            assert result is True
            mock_makedirs.assert_called_once_with(str(tmp_path), exist_ok=True)

    def test_download_file_client_error(self, s3_service, mock_s3_client):
        """Test file download with ClientError."""
        with patch.object(
            mock_s3_client,
            "download_file",
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Object does not exist"}},
                "download_file",
            ),
        ):
            result = s3_service.download_file(
                s3_key="documents/test.pdf", local_path="/tmp/test.pdf"
            )

            assert result is False

    def test_download_file_no_credentials(self, s3_service, mock_s3_client):
        """Test file download with NoCredentialsError."""
        with patch.object(
            mock_s3_client, "download_file", side_effect=NoCredentialsError()
        ):
            result = s3_service.download_file(
                s3_key="documents/test.pdf", local_path="/tmp/test.pdf"
            )

            assert result is False

    def test_get_object_success(self, s3_service, mock_s3_client):
        """Test successful object retrieval from S3."""
        mock_response = {
            "Body": Mock(),
            "ContentType": "application/pdf",
            "ContentLength": 1024,
        }
        with patch.object(mock_s3_client, "get_object", return_value=mock_response):
            result = s3_service.get_object("documents/test.pdf")

            assert result == mock_response
            mock_s3_client.get_object.assert_called_once_with(
                Bucket="test-bucket", Key="documents/test.pdf"
            )

    def test_get_object_client_error(self, s3_service, mock_s3_client):
        """Test object retrieval with ClientError."""
        with patch.object(
            mock_s3_client,
            "get_object",
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Object does not exist"}},
                "get_object",
            ),
        ):
            result = s3_service.get_object("documents/test.pdf")

            assert result is None

    def test_list_objects_success(self, s3_service, mock_s3_client):
        """Test successful object listing from S3."""
        mock_response = {
            "Contents": [
                {"Key": "documents/file1.pdf", "Size": 1024},
                {"Key": "documents/file2.pdf", "Size": 2048},
            ]
        }
        with patch.object(
            mock_s3_client, "list_objects_v2", return_value=mock_response
        ):
            result = s3_service.list_objects(prefix="documents/", max_keys=10)

            assert result == mock_response["Contents"]
            mock_s3_client.list_objects_v2.assert_called_once_with(
                Bucket="test-bucket", Prefix="documents/", MaxKeys=10
            )

    def test_list_objects_empty_bucket(self, s3_service, mock_s3_client):
        """Test object listing for empty bucket."""
        mock_response = {}
        with patch.object(
            mock_s3_client, "list_objects_v2", return_value=mock_response
        ):
            result = s3_service.list_objects()

            assert result == []

    def test_list_objects_client_error(self, s3_service, mock_s3_client):
        """Test object listing with ClientError."""
        with patch.object(
            mock_s3_client,
            "list_objects_v2",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                "list_objects_v2",
            ),
        ):
            result = s3_service.list_objects()

            assert result == []

    def test_list_objects_no_credentials(self, s3_service, mock_s3_client):
        """Test object listing with NoCredentialsError."""
        with patch.object(
            mock_s3_client, "list_objects_v2", side_effect=NoCredentialsError()
        ):
            result = s3_service.list_objects()

            assert result == []

    def test_delete_object_success(self, s3_service, mock_s3_client):
        """Test successful object deletion from S3."""
        result = s3_service.delete_object("documents/test.pdf")

        assert result is True

    def test_delete_object_client_error(self, s3_service, mock_s3_client):
        """Test object deletion with ClientError."""
        with patch.object(
            mock_s3_client,
            "delete_object",
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Object does not exist"}},
                "delete_object",
            ),
        ):
            result = s3_service.delete_object("documents/test.pdf")

            assert result is False

    def test_delete_object_no_credentials(self, s3_service, mock_s3_client):
        """Test object deletion with NoCredentialsError."""
        with patch.object(
            mock_s3_client, "delete_object", side_effect=NoCredentialsError()
        ):
            result = s3_service.delete_object("documents/test.pdf")

            assert result is False

    def test_object_exists_true(self, s3_service, mock_s3_client, tmp_path):
        """Test object existence check when object exists."""
        # First upload a file to S3
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")
        s3_service.upload_file(str(test_file), "documents/test.pdf")

        # Now check if it exists
        result = s3_service.object_exists("documents/test.pdf")

        assert result is True

    def test_object_exists_false_404(self, s3_service, mock_s3_client):
        """Test object existence check when object doesn't exist (404)."""
        with patch.object(
            mock_s3_client,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}}, "head_object"
            ),
        ):
            result = s3_service.object_exists("documents/test.pdf")

            assert result is False

    def test_object_exists_client_error(self, s3_service, mock_s3_client):
        """Test object existence check with other ClientError."""
        with patch.object(
            mock_s3_client,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                "head_object",
            ),
        ):
            result = s3_service.object_exists("documents/test.pdf")

            assert result is False

    def test_object_exists_no_credentials(self, s3_service, mock_s3_client):
        """Test object existence check with NoCredentialsError."""
        with patch.object(
            mock_s3_client, "head_object", side_effect=NoCredentialsError()
        ):
            result = s3_service.object_exists("documents/test.pdf")

            assert result is False

    def test_get_presigned_url_success(self, s3_service, mock_s3_client):
        """Test successful presigned URL generation."""
        with patch.object(
            mock_s3_client,
            "generate_presigned_url",
            return_value="https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123",
        ):
            result = s3_service.get_presigned_url("documents/test.pdf", expiration=7200)

            assert (
                result
                == "https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123"
            )
            mock_s3_client.generate_presigned_url.assert_called_once_with(
                "get_object",
                Params={"Bucket": "test-bucket", "Key": "documents/test.pdf"},
                ExpiresIn=7200,
            )

    def test_get_presigned_url_default_expiration(self, s3_service, mock_s3_client):
        """Test presigned URL generation with default expiration."""
        with patch.object(
            mock_s3_client,
            "generate_presigned_url",
            return_value="https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123",
        ):
            result = s3_service.get_presigned_url("documents/test.pdf")

            assert (
                result
                == "https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123"
            )
            mock_s3_client.generate_presigned_url.assert_called_once_with(
                "get_object",
                Params={"Bucket": "test-bucket", "Key": "documents/test.pdf"},
                ExpiresIn=3600,  # Default expiration
            )

    def test_get_presigned_url_client_error(self, s3_service, mock_s3_client):
        """Test presigned URL generation with ClientError."""
        with patch.object(
            mock_s3_client,
            "generate_presigned_url",
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Object does not exist"}},
                "generate_presigned_url",
            ),
        ):
            result = s3_service.get_presigned_url("documents/test.pdf")

            assert result is None

    def test_get_presigned_url_no_credentials(self, s3_service, mock_s3_client):
        """Test presigned URL generation with NoCredentialsError."""
        with patch.object(
            mock_s3_client, "generate_presigned_url", side_effect=NoCredentialsError()
        ):
            result = s3_service.get_presigned_url("documents/test.pdf")

            assert result is None

    def test_integration_workflow(self, s3_service, mock_s3_client, tmp_path):
        """Test a complete workflow: upload, check existence, get presigned URL, delete."""
        # Create a temporary file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        # Mock successful operations
        with patch.object(
            mock_s3_client,
            "generate_presigned_url",
            return_value="https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123",
        ):
            # Upload file
            result1 = s3_service.upload_file(
                file_path=str(test_file),
                s3_key="documents/test.pdf",
                content_type="application/pdf",
            )
            assert result1 is True

            # Check if file exists
            result2 = s3_service.object_exists("documents/test.pdf")
            assert result2 is True

            # Get presigned URL
            result3 = s3_service.get_presigned_url("documents/test.pdf")
            assert (
                result3
                == "https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123"
            )

            # Delete file
            result4 = s3_service.delete_object("documents/test.pdf")
            assert result4 is True

            # All operations completed successfully
            pass


class TestS3ServiceErrorHandling:
    """Test error handling scenarios for S3Service."""

    def test_upload_file_with_nonexistent_file(self, s3_service, mock_s3_client):
        """Test upload_file with a file that doesn't exist."""
        with patch.object(
            mock_s3_client,
            "upload_file",
            side_effect=FileNotFoundError("No such file or directory"),
        ):
            result = s3_service.upload_file(
                file_path="/nonexistent/file.pdf", s3_key="documents/test.pdf"
            )

            # Should return False when file doesn't exist
            assert result is False

    def test_download_file_with_nested_path(self, s3_service, mock_s3_client, tmp_path):
        """Test download_file with nested directory path."""
        # First upload a file to S3
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")
        s3_service.upload_file(str(test_file), "documents/2025/january/test.pdf")

        # Now download it
        download_path = tmp_path / "2025" / "january" / "test.pdf"
        result = s3_service.download_file(
            s3_key="documents/2025/january/test.pdf", local_path=str(download_path)
        )

        assert result is True

    def test_list_objects_with_large_max_keys(self, s3_service, mock_s3_client):
        """Test list_objects with a large max_keys value."""
        mock_response = {"Contents": []}
        with patch.object(
            mock_s3_client, "list_objects_v2", return_value=mock_response
        ):
            result = s3_service.list_objects(max_keys=10000)

            assert result == []
            mock_s3_client.list_objects_v2.assert_called_once_with(
                Bucket="test-bucket", Prefix="", MaxKeys=10000
            )

    def test_object_exists_with_special_characters(
        self, s3_service, mock_s3_client, tmp_path
    ):
        """Test object_exists with S3 key containing special characters."""
        # First upload a file to S3 with special characters in the key
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")
        s3_service.upload_file(str(test_file), "documents/test file (1).pdf")

        # Now check if it exists
        result = s3_service.object_exists("documents/test file (1).pdf")

        assert result is True


class TestS3ServiceEdgeCases:
    """Test edge cases and boundary conditions for S3Service."""

    def test_upload_fileobj_with_empty_file(self, s3_service, mock_s3_client):
        """Test upload_fileobj with an empty file object."""
        empty_file = io.BytesIO(b"")

        result = s3_service.upload_fileobj(
            file_obj=empty_file, s3_key="documents/empty.txt"
        )

        assert result is True

    def test_list_objects_with_empty_prefix(self, s3_service, mock_s3_client):
        """Test list_objects with empty prefix."""
        mock_response = {"Contents": []}
        with patch.object(
            mock_s3_client, "list_objects_v2", return_value=mock_response
        ):
            result = s3_service.list_objects(prefix="")

            assert result == []
            mock_s3_client.list_objects_v2.assert_called_once_with(
                Bucket="test-bucket", Prefix="", MaxKeys=1000
            )

    def test_get_presigned_url_with_zero_expiration(self, s3_service, mock_s3_client):
        """Test get_presigned_url with zero expiration."""
        with patch.object(
            mock_s3_client,
            "generate_presigned_url",
            return_value="https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123",
        ):
            result = s3_service.get_presigned_url("documents/test.pdf", expiration=0)

            assert (
                result
                == "https://test-bucket.s3.amazonaws.com/documents/test.pdf?signature=abc123"
            )
            mock_s3_client.generate_presigned_url.assert_called_once_with(
                "get_object",
                Params={"Bucket": "test-bucket", "Key": "documents/test.pdf"},
                ExpiresIn=0,
            )

    def test_delete_nonexistent_object(self, s3_service, mock_s3_client):
        """Test delete_object with a nonexistent object."""
        result = s3_service.delete_object("documents/nonexistent.pdf")

        assert result is True
        # S3 delete_object doesn't fail if object doesn't exist
