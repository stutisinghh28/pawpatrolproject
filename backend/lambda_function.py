"""
PawPatrol - AWS Lambda Backend Service
Runtime: Python 3.14 (x86_64)
Integrations: Amazon DynamoDB, Amazon S3 (Pre-signed URLs), Amazon SNS (Urgent Alerts)
"""

import json
import os
import time
import uuid
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError

# Environment variables with sensible defaults
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'PawPatrol-Reports')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET', '')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-1')

# Initialize AWS SDK clients lazily
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
sns_client = boto3.client('sns', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# Helper: JSON Encoder for DynamoDB Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def build_response(status_code, body):
    """Formats an HTTP response with CORS headers for Lambda Function URL or API Gateway."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'OPTIONS,GET,POST,PATCH,PUT,DELETE'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }

def calculate_risk(condition, symptoms, is_trapped, animal_age):
    """
    Deterministic rule-based risk classification logic.
    Scores incidents and categorizes into: CRITICAL, HIGH, MEDIUM, LOW.
    """
    score = 0
    reasons = []

    condition_map = {
        'CRITICAL_INJURY': (8, 'Severe trauma / life-threatening injury'),
        'MODERATE_INJURY': (4, 'Moderate injury or acute illness'),
        'SKIN_OR_SICK': (2, 'Skin condition or chronic illness'),
        'HEALTHY_STRAY': (1, 'Healthy stray routine triage')
    }
    pts, reason = condition_map.get(condition, (1, 'General report'))
    score += pts
    reasons.append(reason)

    symptoms_set = set(symptoms or [])
    if 'unconscious' in symptoms_set:
        score += 10
        reasons.append('Animal is unconscious / unresponsive')
    if 'bleeding_heavily' in symptoms_set:
        score += 6
        reasons.append('Heavy active bleeding')
    if 'hit_by_vehicle' in symptoms_set:
        score += 5
        reasons.append('Hit by motor vehicle')
    if 'broken_bone' in symptoms_set:
        score += 4
        reasons.append('Suspected fractured limb')
    if 'rabies_symptoms' in symptoms_set:
        score += 6
        reasons.append('Neurological or suspected rabies signs')
    if 'skin_mange' in symptoms_set:
        score += 2
        reasons.append('Mange / severe skin disease')
    if 'severe_malnutrition' in symptoms_set:
        score += 3
        reasons.append('Severe dehydration / emaciation')

    if is_trapped:
        score += 4
        reasons.append('Trapped in dangerous hazard')
    if animal_age == 'infant':
        score += 2
        reasons.append('Vulnerable infant (puppy/kitten)')

    if score >= 12 or 'unconscious' in symptoms_set or ('bleeding_heavily' in symptoms_set and ('hit_by_vehicle' in symptoms_set or condition == 'CRITICAL_INJURY')):
        level = 'CRITICAL'
    elif score >= 7 or 'broken_bone' in symptoms_set or 'hit_by_vehicle' in symptoms_set:
        level = 'HIGH'
    elif score >= 4 or 'skin_mange' in symptoms_set or is_trapped:
        level = 'MEDIUM'
    else:
        level = 'LOW'

    return level, score, reasons

def send_sns_emergency_alert(report):
    """Publishes notification to SNS when risk is Critical or High."""
    if not SNS_TOPIC_ARN:
        return

    subject = f"[PawPatrol EMERGENCY] {report['risk_level']} - {report['animal_type']} Rescue"
    message = (
        f"🚨 EMERGENCY RESCUE ALERT\n\n"
        f"Priority: {report['risk_level']} (Score: {report['risk_score']})\n"
        f"Animal: {report['animal_type']} ({report.get('animal_age', 'adult')})\n"
        f"Location: {report['location_address']}\n"
        f"GPS: {report.get('latitude')}, {report.get('longitude')}\n"
        f"Description: {report['description']}\n"
        f"Reporter: {report.get('reporter_name')} ({report.get('reporter_phone')})\n"
        f"Tracking ID: {report['report_id']}\n"
    )

    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message
        )
    except Exception as e:
        print(f"Failed to publish SNS alert: {str(e)}")

def handle_create_report(body_data):
    """Validates, calculates risk, and inserts report into DynamoDB."""
    animal_type = body_data.get('animal_type')
    location_address = body_data.get('location_address')
    description = body_data.get('description')

    if not animal_type or not location_address or not description:
        return build_response(400, {'error': 'Missing required fields: animal_type, location_address, description'})

    condition = body_data.get('condition', 'HEALTHY_STRAY')
    symptoms = body_data.get('symptoms', [])
    is_trapped = bool(body_data.get('is_trapped', False))
    animal_age = body_data.get('animal_age', 'adult')

    # Calculate authoritative server-side risk
    risk_level, risk_score, risk_reasons = calculate_risk(condition, symptoms, is_trapped, animal_age)

    # Unique ID format: PAW-YYYYMMDD-XXXX
    date_str = time.strftime('%Y%m%d')
    rand_str = uuid.uuid4().hex[:5].upper()
    report_id = f"PAW-{date_str}-{rand_str}"
    now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    item = {
        'report_id': report_id,
        'created_at': now_iso,
        'updated_at': now_iso,
        'status': 'REPORTED',
        'animal_type': str(animal_type),
        'animal_age': str(animal_age),
        'condition': str(condition),
        'symptoms': [str(s) for s in symptoms],
        'is_trapped': is_trapped,
        'description': str(description),
        'location_address': str(location_address),
        'reporter_name': str(body_data.get('reporter_name', 'Anonymous Citizen')),
        'reporter_phone': str(body_data.get('reporter_phone', '')),
        'risk_level': risk_level,
        'risk_score': risk_score,
        'risk_reasons': risk_reasons,
        'photo_url': body_data.get('photo_url'),
        'photo_data': body_data.get('photo_data') if not body_data.get('photo_url') else None
    }

    if body_data.get('latitude') is not None:
        item['latitude'] = Decimal(str(body_data['latitude']))
    if body_data.get('longitude') is not None:
        item['longitude'] = Decimal(str(body_data['longitude']))

    try:
        table.put_item(Item=item)
    except Exception as e:
        print(f"DynamoDB PutItem Error: {str(e)}")
        return build_response(500, {'error': f'DynamoDB storage failure: {str(e)}'})

    # Dispatch SNS alert if urgent
    if risk_level in ('CRITICAL', 'HIGH'):
        send_sns_emergency_alert(item)

    return build_response(201, {
        'success': True,
        'message': 'Rescue report created successfully',
        'report': item
    })

def handle_get_reports(query_params):
    """Scans and retrieves reports with optional query parameter filters."""
    query_params = query_params or {}
    risk_filter = query_params.get('risk_level')
    status_filter = query_params.get('status')
    animal_filter = query_params.get('animal_type')

    try:
        scan_kwargs = {}
        # In a high-scale production system, use GSI queries.
        # For our table, scan with limit provides fast retrieval.
        response = table.scan(Limit=100)
        items = response.get('Items', [])

        # In-memory filter & sort by created_at desc
        if risk_filter and risk_filter != 'ALL':
            items = [it for it in items if it.get('risk_level') == risk_filter]
        if status_filter and status_filter != 'ALL':
            items = [it for it in items if it.get('status') == status_filter]
        if animal_filter and animal_filter != 'ALL':
            items = [it for it in items if it.get('animal_type') == animal_filter]

        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return build_response(200, {
            'success': True,
            'reports': items,
            'count': len(items)
        })
    except Exception as e:
        print(f"DynamoDB Scan Error: {str(e)}")
        return build_response(500, {'error': f'Failed to retrieve reports: {str(e)}'})

def handle_update_status(report_id, body_data):
    """Updates status or volunteer notes for an existing report."""
    new_status = body_data.get('status')
    if not new_status:
        return build_response(400, {'error': 'Missing status field'})

    now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    try:
        response = table.update_item(
            Key={'report_id': report_id},
            UpdateExpression='SET #st = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={
                ':status': new_status,
                ':updated_at': now_iso
            },
            ReturnValues='ALL_NEW'
        )
        return build_response(200, {
            'success': True,
            'message': 'Status updated',
            'report': response.get('Attributes')
        })
    except Exception as e:
        print(f"DynamoDB Update Error: {str(e)}")
        return build_response(500, {'error': f'Failed to update report: {str(e)}'})

def handle_generate_upload_url(body_data):
    """Generates an S3 Pre-signed URL for direct browser-to-S3 photo uploads."""
    if not S3_BUCKET_NAME:
        return build_response(503, {'error': 'S3 bucket is not configured on this environment'})

    filename = body_data.get('filename', 'photo.jpg')
    content_type = body_data.get('content_type', 'image/jpeg')
    file_ext = filename.split('.')[-1] if '.' in filename else 'jpg'
    key = f"uploads/{uuid.uuid4().hex}.{file_ext}"

    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': S3_BUCKET_NAME,
                'Key': key,
                'ContentType': content_type
            },
            ExpiresIn=300
        )
        final_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
        return build_response(200, {
            'upload_url': presigned_url,
            'photo_url': final_url,
            'key': key
        })
    except ClientError as e:
        return build_response(500, {'error': f'Failed to generate upload URL: {str(e)}'})

def lambda_handler(event, context):
    """Main AWS Lambda entry point."""
    print(f"Incoming Event: {json.dumps(event, default=str)}")

    # Extract HTTP method and path across Function URL / API Gateway payload formats
    http_method = event.get('requestContext', {}).get('http', {}).get('method') or event.get('httpMethod', 'GET')
    raw_path = event.get('rawPath') or event.get('path', '/')

    # Handle CORS preflight
    if http_method == 'OPTIONS':
        return build_response(200, {'message': 'OK'})

    # Normalize body data
    body = event.get('body')
    body_data = {}
    if body:
        try:
            if isinstance(body, str):
                body_data = json.loads(body)
            else:
                body_data = body
        except Exception:
            body_data = {}

    query_params = event.get('queryStringParameters') or {}

    # Routing
    if raw_path.endswith('/reports') or raw_path == '/reports' or raw_path == '/api/reports':
        if http_method == 'POST':
            return handle_create_report(body_data)
        elif http_method == 'GET':
            return handle_get_reports(query_params)

    elif '/reports/' in raw_path:
        # Extract report_id from path
        report_id = raw_path.split('/reports/')[-1].split('/')[0]
        if http_method == 'PATCH':
            return handle_update_status(report_id, body_data)
        elif http_method == 'GET':
            try:
                res = table.get_item(Key={'report_id': report_id})
                item = res.get('Item')
                if not item:
                    return build_response(404, {'error': 'Report not found'})
                return build_response(200, {'success': True, 'report': item})
            except Exception as e:
                return build_response(500, {'error': str(e)})

    elif raw_path.endswith('/upload-url') or raw_path == '/api/upload-url':
        if http_method == 'POST':
            return handle_generate_upload_url(body_data)

    # Fallback default health check
    return build_response(200, {
        'status': 'online',
        'service': 'PawPatrol Rescue Backend',
        'runtime': 'Python 3.14 (x86_64)',
        'region': AWS_REGION,
        'table': DYNAMODB_TABLE_NAME
    })
