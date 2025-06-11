import os
import boto3
from botocore.exceptions import ClientError
import uuid
import json
import time
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME'))
max_attempts = 5
ttl_seconds = 60 * 60  # 60 minutes
expiration_time = int(time.time()) + ttl_seconds
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN')

def lambda_handler(event, context):
	attempt = 0

	while attempt < max_attempts:
		group_id = str(uuid.uuid4())
		try:
			table.put_item(
				Item={
					'groupId': group_id,
					'createdAt': datetime.utcnow().isoformat(),
					'expiresAt': expiration_time,  # ⏳ DynamoDB TTL attribute
				},
				ConditionExpression='attribute_not_exists(groupId)'
			)
			return build_response(200, {
				'groupId': group_id
			})
		except ClientError as e:
			if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
				attempt += 1 # Collision, try again
				continue
			else:
				return build_response(500, {
					'errorMessage': f'Unexpected error while accessing the database, details: {str(e)}'
				})

	# Too many collisions, something went wrong
	return build_response(500, {
		'errorMessage': 'Could not generate a unique groupId after multiple attempts.'
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
