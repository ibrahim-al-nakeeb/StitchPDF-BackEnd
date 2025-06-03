import boto3
import csv
import io
import time
from datetime import datetime
from PyPDF2 import PdfMerger
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
VALID_BUCKET = os.environ['VALID_FILES_BUCKET']
INVALID_BUCKET = os.environ['INVALID_FILES_BUCKET']

def lambda_handler(event, context):
    try:
        bucket, key = extract_s3_info(event)
        group_id = extract_group_id_from_csv(bucket, key)
        files = list_files_with_group_id(bucket, group_id, exclude_key=key)

        try:
            merged_pdf = merge_files_by_date(bucket, files)
        except Exception:
            handle_merge_failure(bucket, files, group_id)
            return error(f"Failed to merge PDFs.", 500)

        output_key = f"{group_id}/merged_output.pdf"
        upload_merged_file(VALID_BUCKET, output_key, merged_pdf)

        return success(f"Merged {len(files)} PDFs into {output_key}")

    except Exception as e:
        return error(str(e), 500)

# --- Helpers ---

def extract_s3_info(event):
    try:
        record = event['Records'][0]
        return record['s3']['bucket']['name'], record['s3']['object']['key']
    except (KeyError, IndexError):
        raise ValueError("Invalid S3 event structure")

def extract_group_id_from_csv(bucket, key):
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj['Body'].read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        first_row = next(reader, None)
        if not first_row or 'groupId' not in first_row:
            raise ValueError("CSV is missing 'groupId'")
        return first_row['groupId']
    except Exception:
        raise RuntimeError("Failed to read or parse groupId from CSV")

def list_files_with_group_id(bucket, group_id, exclude_key=None):
    try:
        paginator = s3.get_paginator('list_objects_v2')
        response_iterator = paginator.paginate(Bucket=bucket, Prefix=group_id)
        files = []
        for page in response_iterator:
            for obj in page.get('Contents', []):
                if obj['Key'] != exclude_key and obj['Key'].endswith('.pdf'):
                    files.append({'Key': obj['Key'], 'LastModified': obj['LastModified']})
        return sorted(files, key=lambda x: x['LastModified'])
    except ClientError as e:
        raise RuntimeError(f"Error listing S3 objects: {str(e)}")

def merge_files(bucket, files):
    merger = PdfMerger()

    try:
        for file in files:
            obj = s3.get_object(Bucket=bucket, Key=file['Key'])
            stream = io.BytesIO(obj['Body'].read())
            merger.append(stream)

        output = io.BytesIO()
        merger.write(output)
        merger.close()
        output.seek(0)
        return output.read()

    except Exception as e:
        merger.close()
        raise RuntimeError(f"Failed to merge PDF: {str(e)}")

