import logging
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile, HTTPException
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from config import settings

logger = logging.getLogger(__name__)

AWS_ACCESS_KEY_ID=settings.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=settings.AWS_SECRET_ACCESS_KEY
AWS_REGION=settings.AWS_DEFAULT_REGION
AWS_S3_BUCKET_NAME=settings.S3_BUCKET_NAME


class S3Service:
    def __init__(self):
        """Initialize the S3 client with AWS credentials from config."""
        logger.info("Initializing S3Service...")
        try:
            # Check if config values are loaded
            if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, AWS_S3_BUCKET_NAME]):
                 raise ValueError("One or more AWS config variables are missing.")

            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            self.bucket_name = AWS_S3_BUCKET_NAME
            logger.info(f"S3 client initialized for bucket '{self.bucket_name}' in region '{AWS_REGION}'.")
        except ValueError as e:
             logger.error(f"S3 Configuration Error: {e}")
             # Raise config error - prevents app from starting potentially
             raise ValueError(f"S3 Configuration Error: {e}")
        except Exception as e: # Catch other potential Boto3 init errors
            logger.error(f"Failed to initialize S3 client: {e}", exc_info=True)
            # Raising ValueError or a custom ConfigError might be better than HTTPException here
            raise ConnectionError(f"S3 client initialization failed: {e}")

    def _generate_s3_key(self, filename: str) -> str:
        """Generates a unique S3 key, preventing collisions and using UUID."""
        extension = Path(filename).suffix
        return f"media/{uuid.uuid4()}{extension}" # Simple unique key: media/uuid.ext

    async def upload_file(self, file: UploadFile, filename: str, content_type: str) -> str:
        """
        Uploads a file stream (UploadFile) efficiently to S3 using upload_fileobj
        and returns the unique object key. Runs sync Boto3 call in a threadpool.
        """
        if not file or not filename or not content_type:
             logger.warning("Upload attempt with missing file data.")
             raise HTTPException(status_code=400, detail="Missing file, filename, or content type.")

        object_key = self._generate_s3_key(filename)
        logger.info(f"Attempting upload for '{filename}' to S3 key '{object_key}'")

        try:
            await run_in_threadpool(
                self.s3_client.upload_fileobj,
                file.file,
                self.bucket_name,
                object_key,
                ExtraArgs={
                    'ContentType': content_type
                }
            )

            logger.info(f"Successfully uploaded '{filename}' to S3 key '{object_key}'")
            return object_key
        except ClientError as e:
            logger.error(f"Error uploading '{filename}' (key: {object_key}) to S3: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to upload file to storage.")
        except Exception as e:
            logger.error(f"Unexpected error during upload of '{filename}' (key: {object_key}): {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected error occurred during file upload.")
        finally:
            try:
                 await file.close()
            except Exception as close_err:
                 logger.warning(f"Error closing file object for {filename}: {close_err}", exc_info=True)



    def get_presigned_url(self, object_key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for downloading a private file from S3."""
        logger.info(f"Generating presigned URL for S3 key '{object_key}'")
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expiration # Time in seconds url is valid
            )
            logger.info(f"Generated presigned URL for '{object_key}'")
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL for '{object_key}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to generate file access URL.")
        except Exception as e:
             logger.error(f"Unexpected error generating presigned URL for '{object_key}': {e}", exc_info=True)
             raise HTTPException(status_code=500, detail="An unexpected error occurred generating file access URL.")
