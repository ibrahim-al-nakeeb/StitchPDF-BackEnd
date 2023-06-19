import json
import boto3
import urllib.parse
import PyPDF2
import io
import csv

s3 = boto3.client('s3')


def get_session_tag(bucket, key):
    text_file_object = s3.get_object(Bucket=bucket, Key=key)
    text_data = text_file_object['Body'].read().decode('utf-8')
    reader = csv.DictReader(text_data.splitlines())
    row = next(reader, None)  # Read the first row
    return row['session_tag']


def filter_object_by_tag(Bucket, Key, Value):
    # Retrieve all objects in the bucket
    response = s3.list_objects_v2(Bucket=Bucket)
    # Filter objects based on the specified tag
    tagged_file_list = []
    for obj in response['Contents']:
        object_tags = s3.get_object_tagging(Bucket=Bucket,Key=obj['Key'])
        for tag_set in object_tags['TagSet']:
            if(tag_set['Key'] == Key and tag_set['Value'] == Value and obj['Key'].endswith('.pdf')):
                tagged_file_list.append(obj)
                break
    tagged_file_list = sorted(tagged_file_list, key=lambda x: x['LastModified'])
    tagged_file_list = [obj['Key'] for obj in tagged_file_list]
    return tagged_file_list


def merge_pdf_files(bucket, file_keys):
    pdf_merger = PyPDF2.PdfMerger()

    for file_key in file_keys:
        response = s3.get_object(Bucket=bucket, Key=file_key)
        pdf_file = response['Body'].read()
        pdf_stream = io.BytesIO(pdf_file)
        pdf_merger.append(pdf_stream)
    merged_pdf = io.BytesIO()
    pdf_merger.write(merged_pdf)
    merged_pdf.seek(0)
    merged_pdf_bytes = merged_pdf.getvalue()
    return merged_pdf


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
