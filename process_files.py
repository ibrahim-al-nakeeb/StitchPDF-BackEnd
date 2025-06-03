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
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    try:
        session_tag_val = get_session_tag(bucket, key)
        tagged_file_list = filter_object_by_tag(bucket, 'session_tag', session_tag_val)
        merged_file = merge_pdf_files(bucket, tagged_file_list)
        s3.put_object(Body=merged_file, Bucket='merge-wizard-pdf-merged-files', Key='{}.pdf'.format(session_tag_val))
        tagged_file_list.append(key)
        [s3.delete_object(Bucket=bucket,Key=key,) for key in tagged_file_list]
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
