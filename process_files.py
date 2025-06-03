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

    except Exception as e:
        error_message = 'An error occurred while processing the request. Please try again later. Error details: {}'.format(str(e), e)
        print(error_message)
        if(tagged_file_list):
            tagged_file_list.append(key)
            corrupted_files = [s3.get_object(Bucket=bucket, Key=file_key) for file_key in tagged_file_list]
            print(tagged_file_list)
            print(corrupted_files)
            [s3.put_object(Body=file['Body'].read(), Bucket='merge-wizard-pdf-invalid-files', Key=file_key) for file, file_key in zip(corrupted_files, tagged_file_list)]
            print("put_object")
            [s3.delete_object(Bucket=bucket,Key=key,) for key in tagged_file_list]
            print("delete_object")
