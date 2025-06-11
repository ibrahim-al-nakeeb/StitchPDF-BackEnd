import json
import boto3
import os

s3_client = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME')
EXPIRATION = os.environ.get('EXPIRATION')  # URL expiration time in seconds
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN')

def lambda_handler(event, context):
	query = event.get('queryStringParameters') or {}
	group_id = query.get('groupId')

	if not group_id:
		return build_response(400, {
			'errorMessage': 'Missing "group_id" in request'
		})

	try:
		url = s3_client.generate_presigned_url(
			ClientMethod='get_object',
			Params={'Bucket': BUCKET, 'Key': f'{group_id}/merged_output.pdf'},
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
