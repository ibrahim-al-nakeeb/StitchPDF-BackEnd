import json
import boto3
import os
import urllib.parse

s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME')
ALLOWED_EXTENSIONS = ['.pdf', '.json']
EXPIRATION = os.environ.get('EXPIRATION')  # URL expiration time in seconds
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN')

def lambda_handler(event, context):
	query = event.get('queryStringParameters') or {}
	key = query.get('filename')

	if not key:
		return build_response(400, {
			'errorMessage': 'Missing "filename" query parameter'
		})

	if not any(key.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
		return build_response(400, {
			'errorMessage': 'Only PDF or JSON files are allowed'
		})

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
		return build_response(500, {
			'errorMessage': str(e)
		})

def build_response(status_code, body):
	return {
		'statusCode': status_code,
		'body': json.dumps(body),
		'headers': {
			'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
			'Content-Type': 'application/json'
		}
	}
