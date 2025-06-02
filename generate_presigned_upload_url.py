import json
import boto3
import os
import urllib.parse

s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME')
ALLOWED_EXTENSIONS = ['.pdf', '.csv']
EXPIRATION = 30  # URL expiration time in seconds

def lambda_handler(event, context):
	query = event.get('queryStringParameters') or {}
	key = query.get('filename')
	tag = query.get('tag')  # e.g., tag=group:id

	if not key or not tag:
		return {
			'statusCode': 400,
			'body': json.dumps({'error': 'Missing "filename" or "tag" query parameter'})
		}

	if not any(key.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
		return {
			'statusCode': 400,
			'body': json.dumps({'error': 'Only PDF or CSV files are allowed'})
		}

	try:
		# Ensure the tag is URL-encoded
		tagging = urllib.parse.quote(tag, safe='=&')

		url = s3.generate_presigned_url(
			ClientMethod='put_object',
			Params={
				'Bucket': BUCKET,
				'Key': key,
				'Tagging': tagging
			},
			ExpiresIn=EXPIRATION
		)

		return {
			'statusCode': 200,
			'headers': {'Access-Control-Allow-Origin': '*'},
			'body': json.dumps({'uploadUrl': url})
		}
	except Exception as e:
		return {
			'statusCode': 500,
			'body': json.dumps({'error': str(e)})
		}
