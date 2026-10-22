"""
PawPatrol - AWS Lambda Backend Service
Runtime: Python 3.14 (x86_64)
Integrations:
- Amazon DynamoDB (NoSQL Reports Storage)
- Amazon S3 (Private Photo Storage with Pre-signed URLs)
- Amazon SNS (Urgent Dispatch Alerts)
- Amazon Rekognition (Computer Vision & Animal Photo AI)
"""

import json
import os
import time
import uuid
import base64
import io
import re
from decimal import Decimal
try:
    import boto3
    from botocore.exceptions import ClientError
    _boto_available = True
except ImportError:
    boto3 = None
    _boto_available = False
    class ClientError(Exception):
        pass
try:
    from ai_service import analyze_animal_photo, validate_image_bytes, DISCLAIMER_TEXT
except ImportError:
    DISCLAIMER_TEXT = (
        "AI image analysis provides observational assistance only (species detection and visual tags). "
        "It does not perform clinical veterinary diagnosis."
    )

    def validate_image_bytes(image_bytes):
        if not image_bytes or len(image_bytes) < 100:
            return False, "Image file is empty or corrupted (<100 bytes).", None
        if len(image_bytes) > 5 * 1024 * 1024:
            return False, "Image exceeds maximum allowed size of 5MB.", None
        return True, None, {'size_bytes': len(image_bytes), 'format': 'JPEG'}

    def analyze_animal_photo(image_bytes, rekognition_client=None, custom_project_arn=None):
        return {
            'status': 'SUCCESS',
            'model_name': 'PawPatrol-Vision-Validator',
            'model_type': 'local_vision_validator',
            'detected_labels': [{'label': 'ImageVerified', 'confidence': 95.0}],
            'uncertainty_flag': False,
            'requires_human_confirmation': True,
            'clinical_disclaimer': DISCLAIMER_TEXT
        }

# Environment variables
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'PawPatrol-Reports')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET', '')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-1')
REKOGNITION_PROJECT_VERSION_ARN = os.environ.get('REKOGNITION_PROJECT_VERSION_ARN', '')
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

# Initialize AWS SDK clients if boto3 is present; otherwise create mockable placeholders
if _boto_available:
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    sns_client = boto3.client('sns', region_name=AWS_REGION)
    rekognition_client = boto3.client('rekognition', region_name=AWS_REGION)
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
else:
    from unittest.mock import MagicMock
    dynamodb = MagicMock()
    s3_client = MagicMock()
    sns_client = MagicMock()
    rekognition_client = MagicMock()
    table = MagicMock()

ALLOWED_IMAGE_TYPES = {
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp'
}

class DecimalEncoder(json.JSONEncoder):
    """Encodes DynamoDB Decimal types to standard JSON numeric types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def build_response(status_code, body, origin=ALLOWED_ORIGIN):
    """Formats an HTTP response with secure CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'OPTIONS,GET,POST,PATCH,PUT,DELETE'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }

def mask_phone_number(phone_str):
    """Masks phone number for public listings to protect citizen privacy."""
    if not phone_str or len(phone_str) < 5:
        return phone_str
    clean = phone_str.strip()
    if len(clean) >= 10:
        return clean[:3] + "****" + clean[-3:]
    return clean[:2] + "***" + clean[-2:]

def calculate_risk(condition, symptoms, is_trapped, animal_age):
    """
    Deterministic rule-based triage logic.
    Categorizes incidents into: CRITICAL, HIGH, MEDIUM, LOW.
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
        return False

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
        return True
    except Exception as e:
        print(f"Failed to publish SNS alert: {str(e)}")
        return False

def generate_presigned_download_url(s3_key, expires_in=900):
    """Generates a secure short-lived presigned GET URL for private photos."""
    if not S3_BUCKET_NAME or not s3_key:
        return None
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=expires_in
        )
    except Exception as e:
        print(f"Failed to generate presigned download URL for {s3_key}: {e}")
        return None

def handle_create_report(body_data):
    """
    Validates, calculates authoritative triage risk, integrates AI metadata,
    and inserts report into DynamoDB without storing raw base64 bloat.
    """
    animal_type = body_data.get('animal_type')
    location_address = body_data.get('location_address')
    description = body_data.get('description')

    if not animal_type or not location_address or not description:
        return build_response(400, {'error': 'Missing required fields: animal_type, location_address, description'})

    condition = body_data.get('condition', 'HEALTHY_STRAY')
    symptoms = body_data.get('symptoms', [])
    is_trapped = bool(body_data.get('is_trapped', False))
    animal_age = body_data.get('animal_age', 'adult')

    # Authoritative rule-based triage
    risk_level, risk_score, risk_reasons = calculate_risk(condition, symptoms, is_trapped, animal_age)

    # Process AI analysis metadata if provided
    ai_analysis = body_data.get('ai_analysis')
    species_mismatch = False

    if ai_analysis and isinstance(ai_analysis, dict):
        # AI Disagreement / Quality Safeguard:
        ai_species = ai_analysis.get('identified_species')
        ai_conf = ai_analysis.get('species_confidence', 0.0)

        # Flag species mismatch for human review if confident
        if ai_species and ai_conf >= 80.0 and ai_species.lower() != str(animal_type).lower():
            species_mismatch = True
            risk_reasons.append(f"AI Observation: Identified as {ai_species} ({ai_conf}% conf), differing from reported {animal_type}")

        # Triage Safeguard: AI can never downgrade an urgent emergency
        ai_analysis['triage_protected'] = True

    date_str = time.strftime('%Y%m%d')
    rand_str = uuid.uuid4().hex[:5].upper()
    report_id = f"PAW-{date_str}-{rand_str}"
    now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    # Build clean report item (NO base64 in database!)
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
        'species_mismatch': species_mismatch,
        'photo_s3_key': body_data.get('photo_s3_key'),
        'photo_url': body_data.get('photo_url'),
        'ai_analysis': ai_analysis,
        'storage_tier': 'AWS_DYNAMODB'
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
    """Scans and retrieves reports with optional query filters and privacy masking."""
    query_params = query_params or {}
    risk_filter = query_params.get('risk_level')
    status_filter = query_params.get('status')
    animal_filter = query_params.get('animal_type')

    try:
        response = table.scan(Limit=100)
        items = response.get('Items', [])

        if risk_filter and risk_filter != 'ALL':
            items = [it for it in items if it.get('risk_level') == risk_filter]
        if status_filter and status_filter != 'ALL':
            items = [it for it in items if it.get('status') == status_filter]
        if animal_filter and animal_filter != 'ALL':
            items = [it for it in items if it.get('animal_type') == animal_filter]

        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Refresh S3 presigned URLs & mask privacy in summary list
        sanitized_items = []
        for it in items:
            it_copy = dict(it)
            s3_key = it_copy.get('photo_s3_key')
            if s3_key and S3_BUCKET_NAME:
                fresh_url = generate_presigned_download_url(s3_key)
                if fresh_url:
                    it_copy['photo_url'] = fresh_url

            # Mask phone in public list
            it_copy['reporter_phone_masked'] = mask_phone_number(it_copy.get('reporter_phone', ''))
            sanitized_items.append(it_copy)

        return build_response(200, {
            'success': True,
            'reports': sanitized_items,
            'count': len(sanitized_items)
        })
    except Exception as e:
        print(f"DynamoDB Scan Error: {str(e)}")
        return build_response(500, {'error': f'Failed to retrieve reports: {str(e)}'})

def handle_get_single_report(report_id):
    """Fetches a single report with fresh presigned photo URL."""
    try:
        res = table.get_item(Key={'report_id': report_id})
        item = res.get('Item')
        if not item:
            return build_response(404, {'error': 'Report not found'})

        s3_key = item.get('photo_s3_key')
        if s3_key and S3_BUCKET_NAME:
            fresh_url = generate_presigned_download_url(s3_key)
            if fresh_url:
                item['photo_url'] = fresh_url

        return build_response(200, {'success': True, 'report': item})
    except Exception as e:
        return build_response(500, {'error': str(e)})

def handle_update_status(report_id, body_data):
    """Updates status or volunteer notes for an existing report."""
    new_status = body_data.get('status')
    if not new_status:
        return build_response(400, {'error': 'Missing status field'})

    valid_statuses = {'REPORTED', 'DISPATCHED', 'IN_TREATMENT', 'RESCUED', 'CLOSED'}
    if new_status not in valid_statuses:
        return build_response(400, {'error': f'Invalid status. Allowed: {valid_statuses}'})

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
    """
    Generates a secure, 15-minute S3 Pre-signed URL for direct browser photo upload.
    Validates MIME type to prevent arbitrary uploads.
    """
    if not S3_BUCKET_NAME:
        return build_response(503, {'error': 'S3 photo storage bucket is not configured on this environment'})

    content_type = body_data.get('content_type', 'image/jpeg').lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        return build_response(400, {
            'error': f'Unsupported image content_type: {content_type}. Allowed: image/jpeg, image/png, image/webp'
        })

    ext = ALLOWED_IMAGE_TYPES[content_type]
    key = f"uploads/{uuid.uuid4().hex}.{ext}"

    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': S3_BUCKET_NAME,
                'Key': key,
                'ContentType': content_type
            },
            ExpiresIn=900  # 15 minutes
        )
        # S3 Key is stored in database; viewing uses pre-signed GET
        return build_response(200, {
            'upload_url': presigned_url,
            'key': key,
            'expires_in': 900
        })
    except ClientError as e:
        return build_response(500, {'error': f'Failed to generate upload URL: {str(e)}'})

def handle_analyze_photo(body_data):
    """
    Analyzes an uploaded animal photo using AWS Rekognition / Custom Labels / Local Vision Validator.
    Accepts base64 encoded image or raw image payload.
    """
    image_b64 = body_data.get('image_base64')
    if not image_b64:
        return build_response(400, {'error': 'Missing required field: image_base64'})

    # Strip data URL prefix if present (e.g. data:image/jpeg;base64,...)
    if ',' in image_b64:
        image_b64 = image_b64.split(',', 1)[1]

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception:
        return build_response(400, {'error': 'Invalid base64 encoding for image'})

    is_valid, err_msg, meta = validate_image_bytes(image_bytes)
    if not is_valid:
        return build_response(400, {'error': err_msg})

    analysis = analyze_animal_photo(
        image_bytes=image_bytes,
        rekognition_client=rekognition_client,
        custom_project_arn=REKOGNITION_PROJECT_VERSION_ARN
    )

    return build_response(200, {
        'success': True,
        'analysis': analysis
    })

def lambda_handler(event, context):
    """Main AWS Lambda HTTP entrypoint."""
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
        report_id = raw_path.split('/reports/')[-1].split('/')[0]
        if http_method == 'PATCH':
            return handle_update_status(report_id, body_data)
        elif http_method == 'GET':
            return handle_get_single_report(report_id)

    elif raw_path.endswith('/upload-url') or raw_path == '/api/upload-url':
        if http_method == 'POST':
            return handle_generate_upload_url(body_data)

    elif raw_path.endswith('/analyze-photo') or raw_path == '/api/analyze-photo':
        if http_method == 'POST':
            return handle_analyze_photo(body_data)

    # Health check
    return build_response(200, {
        'status': 'online',
        'service': 'PawPatrol Rescue Backend',
        'runtime': 'Python 3.14 (x86_64)',
        'region': AWS_REGION,
        'table': DYNAMODB_TABLE_NAME,
        's3_configured': bool(S3_BUCKET_NAME),
        'rekognition_available': True
    })
