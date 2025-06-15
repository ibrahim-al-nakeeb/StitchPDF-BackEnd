import json
import boto3
import os
import time
from botocore.exceptions import ClientError

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME'))

BUCKET = os.environ.get('BUCKET_NAME')
EXPIRATION = os.environ.get('EXPIRATION') # URL expiration time in seconds
MAX_ATTEMPTS = int(os.environ.get('MAX_ATTEMPTS'))
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN')
WAIT_SECONDS = float(os.environ.get('WAIT_SECONDS'))

def lambda_handler(event, context):
	query = event.get('queryStringParameters') or {}
	group_id = query.get('groupId')

	if not group_id:
		return build_response(400, {
			'errorMessage': 'Missing "group_id" in request'
		})

	key = f'{group_id}/merged_output.pdf'

	for _ in range(MAX_ATTEMPTS):
		try:
			result = table.get_item(Key={'groupId': group_id})
			status = result.get('Item', {}).get('status')

			if status == 'SUCCESS':
				url = s3_client.generate_presigned_url(
					ClientMethod='get_object',
					Params={'Bucket': BUCKET, 'Key': key},
					ExpiresIn=EXPIRATION
				)
				return build_response(200, {'presigned_url': url})

			elif status == 'FAILED':
				return build_response(400, {'errorMessage': 'Merge failed'})

			# else: PENDING or missing, wait and retry
			time.sleep(WAIT_SECONDS)

		except Exception as e:
			return build_response(500, {'errorMessage': str(e)})

	return build_response(202, {'message': 'Still processing, try again later'})

def build_response(status_code, body):
	return {
		'statusCode': status_code,
		'body': json.dumps(body),
		'headers': {
			'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
			'Content-Type': 'application/json'
		}
	}
