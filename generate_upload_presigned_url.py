import json
import boto3
import os
import urllib.parse

s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME')
ALLOWED_EXTENSIONS = ['.pdf', '.json']
EXPIRATION = 30  # URL expiration time in seconds

def lambda_handler(event, context):
	query = event.get('queryStringParameters') or {}
	key = query.get('filename')
	tag = query.get('tag')  # e.g., tag=group:id

	if not key or not tag:
		return {
			'statusCode': 400,
			'body': 'Missing "filename" or "tag" query parameter'
		}

	if not any(key.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
		return {
			'statusCode': 400,
			'body': 'error': 'Only PDF or JSON files are allowed'
		}

	try:
		url = s3.generate_presigned_url(
			ClientMethod='put_object',
			Params={
				'Bucket': BUCKET,
				'Key': key
			},
			ExpiresIn=EXPIRATION
		)

		return build_response(200, {
			'presigned_url': url
		})
	except Exception as e:
		return {
			'statusCode': 500,
			'headers': {
				'Content-Type': 'application/json',
				'Access-Control-Allow-Origin': '*'
			},
			'body': str(e)
		}
