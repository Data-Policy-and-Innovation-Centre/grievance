import boto3
import os
from typing import Optional, Dict, List, BinaryIO
from botocore.exceptions import ClientError, NoCredentialsError
from loguru import logger
from app.config import settings


class S3Service:
    """
    Service class for S3 operations
    """
    def __init__(self, bucket_name: str = None, s3_client: boto3.client = None, s3_resource: boto3.resource = None):
        self.bucket_name = bucket_name or settings.AWS_S3_DOCUMENTS
        self.s3_client = s3_client or boto3.client('s3')
        self.s3_resource = s3_resource or boto3.resource('s3')
        
    def upload_file(self, file_path: str, s3_key: str, content_type: str = None) -> bool:
        """
        Upload a file to S3
        
        Args:
            file_path: Local path to the file
            s3_key: S3 object key (path in bucket)
            content_type: MIME type of the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
                
            self.s3_client.upload_file(
                file_path, 
                self.bucket_name, 
                s3_key,
                ExtraArgs=extra_args
            )
            logger.info(f"Successfully uploaded {file_path} to s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error uploading file to S3: {e}")
            return False
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return False
        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            return False
    
    def upload_fileobj(self, file_obj: BinaryIO, s3_key: str, content_type: str = None) -> bool:
        """
        Upload a file object to S3
        
        Args:
            file_obj: File-like object to upload
            s3_key: S3 object key
            content_type: MIME type of the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
                
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            logger.info(f"Successfully uploaded file object to s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error uploading file object to S3: {e}")
            return False
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return False
    
    def download_file(self, s3_key: str, local_path: str) -> bool:
        """
        Download a file from S3
        
        Args:
            s3_key: S3 object key
            local_path: Local path to save the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            self.s3_client.download_file(
                self.bucket_name,
                s3_key,
                local_path
            )
            logger.info(f"Successfully downloaded s3://{self.bucket_name}/{s3_key} to {local_path}")
            return True
            
        except ClientError as e:
            logger.error(f"Error downloading file from S3: {e}")
            return False
        
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return False
    
    def get_object(self, s3_key: str) -> Optional[Dict]:
        """
        Get an object from S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            Dict: Object data or None if error
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return response
            
        except ClientError as e:
            logger.error(f"Error getting object from S3: {e}")
            return None 
        
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return None
    
    def list_objects(self, prefix: str = "", max_keys: int = 1000) -> List[Dict]:
        """
        List objects in S3 bucket
        
        Args:
            prefix: Prefix to filter objects
            max_keys: Maximum number of keys to return
            
        Returns:
            List: List of object dictionaries
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            return response.get('Contents', [])
            
        except ClientError as e:
            logger.error(f"Error listing objects in S3: {e}")
            return []
        
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return []
    
    def delete_object(self, s3_key: str) -> bool:
        """
        Delete an object from S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            logger.info(f"Successfully deleted s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting object from S3: {e}")
            return False
        
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return False
    
    def object_exists(self, s3_key: str) -> bool:
        """
        Check if an object exists in S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            bool: True if object exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Error checking object existence: {e}")
            return False
        
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return False
    
    def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for S3 object
        
        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds
            
        Returns:
            str: Presigned URL or None if error
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return url
            
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None
        
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return None
