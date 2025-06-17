import boto3
import io
import os
import time
import json
from datetime import datetime
from PyPDF2 import PdfMerger
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME'))

VALID_BUCKET = os.environ['VALID_FILES_BUCKET']
INVALID_BUCKET = os.environ['INVALID_FILES_BUCKET']

def lambda_handler(event, context):
	group_id = None

	try:
		bucket, key = extract_s3_info(event)
		group_id = extract_group_id_from_json(bucket, key)
		files = list_files_with_group_id(bucket, group_id, exclude_key=key)

		try:
			merged_pdf = merge_files(bucket, files)
		except Exception as e:
			handle_merge_failure(bucket, files, group_id)
			raise e

		output_key = f'{group_id}/merged_output.pdf'
		upload_merged_file(VALID_BUCKET, output_key, merged_pdf)
		update_merge_status(group_id, 'SUCCESS')

	except Exception as e:
		update_merge_status(group_id, 'FAILED')
		raise RuntimeError(f'Unexpected error: {str(e)}')

# --- Helpers ---

def extract_s3_info(event):
	try:
		record = event['Records'][0]
		return record['s3']['bucket']['name'], record['s3']['object']['key']
	except (KeyError, IndexError):
		raise ValueError('Invalid S3 event structure')

def extract_group_id_from_json(bucket, key):
	obj = s3.get_object(Bucket=bucket, Key=key)
	content = obj['Body'].read().decode('utf-8')
	data = json.loads(content)

	# Expecting a flat JSON object like: { 'groupId': '...' }
	if 'groupId' not in data:
		raise ValueError('JSON is missing "groupId"')

	return data['groupId']

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
		raise RuntimeError(f'Error listing S3 objects: {str(e)}')

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
		raise RuntimeError(f'Failed to merge PDF: {str(e)}')

def upload_merged_file(bucket, key, content_bytes):
	try:
		s3.put_object(
			Bucket=bucket,
			Key=key,
			Body=content_bytes,
			ContentType='application/pdf'
		)
	except ClientError as e:
		raise RuntimeError(f'Failed to upload merged PDF: {str(e)}')

def handle_merge_failure(bucket, files, group_id):
	for file in files:
		original_key = file['Key']
		filename = original_key.split('/')[-1]
		dest_key = f'{group_id}/{filename}'

		try:
			obj = s3.get_object(Bucket=bucket, Key=original_key)
			s3.put_object(Bucket=INVALID_BUCKET, Key=dest_key, Body=obj['Body'].read())
		except Exception:
			# If even moving fails, skip it, we're already in failure mode
			pass

def update_merge_status(group_id, status):
	table.update_item(
		Key={'groupId': group_id},
		UpdateExpression='SET #s = :s',
		ExpressionAttributeNames={'#s': 'status'},
		ExpressionAttributeValues={':s': status}
	)
