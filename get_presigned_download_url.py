import json
import boto3
import os

s3_client = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME')
EXPIRATION = 30  # URL expiration time in seconds

def lambda_handler(event, context):
	query = event.get('queryStringParameters') or {}
	group_id = query.get('groupId')

	if not group_id:
		return {
			'statusCode': 400,
			'body': json.dumps({'error': 'Missing "group_id" in request'})
		}

	try:
		presigned_url = s3_client.generate_presigned_url(
			ClientMethod='get_object',
			Params={'Bucket': BUCKET_NAME, 'Key': f'{group_id}/merged_output.pdf.pdf'},
			ExpiresIn=EXPIRATION
		)
		
		return {
			'statusCode': 200,
			'body': json.dumps({'presigned_url': presigned_url})
		}
		
	except Exception as e:
		return {
			'statusCode': 500,
			'body': json.dumps({'error': str(e)})
		}
