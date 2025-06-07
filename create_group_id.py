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
			return {
				'statusCode': 200,
				'body': json.dumps({'groupId': group_id})
			}
		except ClientError as e:
			if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
				# ⚠️ Collision, try again
				attempt += 1
				continue
			else:
				# ❌ Other error
				raise

	# ❌ Too many collisions, something is wrong
	return {
		'statusCode': 500,
		'headers': {
			'Access-Control-Allow-Origin': '*'
		},
		'body': 'Could not generate unique groupId'
	}

