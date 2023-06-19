import json
import boto3

s3 = boto3.client('s3')

def lambda_handler(event, context):
    # Extract the "tag" value
    tag = event["tag"]
    
    
    presignedURL = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': 'merge-wizard-pdf-merged-files', 'Key': '{}.pdf'.format(tag)},
        ExpiresIn=30  # URL expiration time in seconds 
    );
    
    response = {
        'presigned_url': presignedURL
        
    }
    
    print(tag)
    
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }