"""
Comprehensive Unit & Integration Test Suite for PawPatrol
Tests:
1. Rule-based Triage Logic (Critical, High, Medium, Low) on both Lambda and Local server
2. Triage Safeguards & Disagreement Handling (AI never downgrades emergency triage)
3. Image Validation & AI Photo Analysis (Rekognition DetectLabels, Custom Labels, Local Vision)
4. Production AWS Lambda Handlers (CRUD, S3 Presigned URLs, SNS Alerting, Error Resilience)
5. Security & Privacy (Reporter phone masking, MIME validation, zero base64 storage)
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import os
import sys
import io
from decimal import Decimal

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lambda_function
import local_server
import ai_service

def create_dummy_jpeg_bytes(width=100, height=100, color=(200, 100, 50)):
    """Creates valid in-memory JPEG bytes with realistic contrast for testing."""
    from PIL import Image, ImageDraw
    bio = io.BytesIO()
    img = Image.new('RGB', (width, height), color=color)
    draw = ImageDraw.Draw(img)
    if width > 20 and height > 20:
        draw.rectangle([5, 5, width // 2, height // 2], fill=(30, 200, 120))
    img.save(bio, format='JPEG')
    return bio.getvalue()

def create_dummy_png_bytes(width=80, height=80):
    from PIL import Image
    bio = io.BytesIO()
    img = Image.new('RGB', (width, height), color=(100, 150, 200))
    img.save(bio, format='PNG')
    return bio.getvalue()


class TestTriageLogic(unittest.TestCase):
    """Verifies deterministic triage scoring rules across both Lambda and Local implementations."""

    def test_critical_unconscious(self):
        """Unconscious animal must always evaluate to CRITICAL priority."""
        for module in [lambda_function, local_server]:
            level, score, reasons = module.calculate_risk('CRITICAL_INJURY', ['unconscious'], False, 'adult')
            self.assertEqual(level, 'CRITICAL', f"Failed for {module.__name__}")
            self.assertGreaterEqual(score, 12)
            self.assertTrue(any('unconscious' in r.lower() for r in reasons))

    def test_critical_vehicular_trauma_and_bleeding(self):
        """Hit by vehicle with active bleeding must be CRITICAL."""
        for module in [lambda_function, local_server]:
            level, score, reasons = module.calculate_risk('CRITICAL_INJURY', ['hit_by_vehicle', 'bleeding_heavily'], False, 'adult')
            self.assertEqual(level, 'CRITICAL', f"Failed for {module.__name__}")
            self.assertGreaterEqual(score, 12)

    def test_high_broken_bone(self):
        """Broken bone or fracture without unconsciousness must evaluate to HIGH priority."""
        for module in [lambda_function, local_server]:
            level, score, reasons = module.calculate_risk('MODERATE_INJURY', ['broken_bone'], False, 'adult')
            self.assertEqual(level, 'HIGH', f"Failed for {module.__name__}")
            self.assertIn(score, range(7, 12))

    def test_high_rabies_symptoms(self):
        """Suspected rabies or acute neurological distress must evaluate to HIGH priority."""
        for module in [lambda_function, local_server]:
            level, score, reasons = module.calculate_risk('MODERATE_INJURY', ['rabies_symptoms'], False, 'adult')
            self.assertEqual(level, 'HIGH', f"Failed for {module.__name__}")
            self.assertIn(score, range(7, 12))

    def test_medium_skin_mange(self):
        """Severe skin mange on adult stray must evaluate to MEDIUM priority."""
        for module in [lambda_function, local_server]:
            level, score, reasons = module.calculate_risk('SKIN_OR_SICK', ['skin_mange'], False, 'adult')
            self.assertEqual(level, 'MEDIUM', f"Failed for {module.__name__}")
            self.assertIn(score, range(4, 7))

    def test_low_healthy_stray(self):
        """Healthy stray animal routine triage must evaluate to LOW priority."""
        for module in [lambda_function, local_server]:
            level, score, reasons = module.calculate_risk('HEALTHY_STRAY', [], False, 'adult')
            self.assertEqual(level, 'LOW', f"Failed for {module.__name__}")
            self.assertLessEqual(score, 3)

    def test_triage_implementation_parity(self):
        """Ensures Lambda and Local Server triage implementations yield identical outputs for any test case."""
        test_cases = [
            ('CRITICAL_INJURY', ['bleeding_heavily', 'unconscious'], True, 'infant'),
            ('MODERATE_INJURY', ['hit_by_vehicle'], False, 'adult'),
            ('SKIN_OR_SICK', ['severe_malnutrition'], False, 'senior'),
            ('HEALTHY_STRAY', [], False, 'adult'),
        ]
        for cond, symp, trapped, age in test_cases:
            l_level, l_score, _ = lambda_function.calculate_risk(cond, symp, trapped, age)
            s_level, s_score, _ = local_server.calculate_risk(cond, symp, trapped, age)
            self.assertEqual(l_level, s_level)
            self.assertEqual(l_score, s_score)


class TestTriageSafeguardsAndDisagreements(unittest.TestCase):
    """Verifies that AI predictions never override or downgrade urgent human rescue triage."""

    def test_ai_uncertainty_preserves_critical_risk(self):
        """Even if AI confidence is low or 0, a critical report remains CRITICAL."""
        payload = {
            'animal_type': 'Dog',
            'location_address': 'Highway 24 Crossing',
            'description': 'Hit by truck, heavy bleeding',
            'condition': 'CRITICAL_INJURY',
            'symptoms': ['hit_by_vehicle', 'bleeding_heavily'],
            'ai_analysis': {
                'status': 'LOW_CONFIDENCE',
                'identified_species': None,
                'species_confidence': 20.0,
                'uncertainty_flag': True
            }
        }
        with patch.object(lambda_function.table, 'put_item') as mock_put, \
             patch.object(lambda_function, 'send_sns_emergency_alert') as mock_sns:
            resp = lambda_function.handle_create_report(payload)
            self.assertEqual(resp['statusCode'], 201)
            body = json.loads(resp['body'])
            report = body['report']
            self.assertEqual(report['risk_level'], 'CRITICAL')
            self.assertGreaterEqual(report['risk_score'], 12)
            mock_sns.assert_called_once()

    def test_species_disagreement_flagging(self):
        """When user reports 'Dog' but AI identifies 'Cat' with 95% confidence, flags mismatch for review."""
        payload = {
            'animal_type': 'Dog',
            'location_address': 'Sector 15 Park',
            'description': 'Small animal found shivering',
            'condition': 'MODERATE_INJURY',
            'symptoms': ['severe_malnutrition'],
            'ai_analysis': {
                'status': 'SUCCESS',
                'identified_species': 'Cat',
                'species_confidence': 95.0,
                'uncertainty_flag': False
            }
        }
        with patch.object(lambda_function.table, 'put_item') as mock_put:
            resp = lambda_function.handle_create_report(payload)
            self.assertEqual(resp['statusCode'], 201)
            body = json.loads(resp['body'])
            report = body['report']
            self.assertTrue(report.get('species_mismatch'), "Species mismatch should be flagged for human review")


class TestImageValidationAndAI(unittest.TestCase):
    """Verifies image validation and the AI computer vision service."""

    def test_valid_jpeg_validation(self):
        jpeg_bytes = create_dummy_jpeg_bytes()
        is_valid, err, meta = ai_service.validate_image_bytes(jpeg_bytes)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        self.assertEqual(meta['format'], 'JPEG')
        self.assertEqual(meta['width'], 100)

    def test_valid_png_validation(self):
        png_bytes = create_dummy_png_bytes()
        is_valid, err, meta = ai_service.validate_image_bytes(png_bytes)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        self.assertEqual(meta['format'], 'PNG')

    def test_corrupt_or_empty_image_rejected(self):
        is_valid, err, _ = ai_service.validate_image_bytes(b"not an image file")
        self.assertFalse(is_valid)
        self.assertIn("corrupted", err.lower())

        is_valid_empty, err_empty, _ = ai_service.validate_image_bytes(b"")
        self.assertFalse(is_valid_empty)

    def test_oversized_image_rejected(self):
        large_bytes = b"0" * (5 * 1024 * 1024 + 100)  # > 5MB
        is_valid, err, _ = ai_service.validate_image_bytes(large_bytes)
        self.assertFalse(is_valid)
        self.assertIn("maximum", err.lower())

    def test_tiny_resolution_rejected(self):
        tiny_bytes = create_dummy_jpeg_bytes(width=16, height=16)
        is_valid, err, _ = ai_service.validate_image_bytes(tiny_bytes)
        self.assertFalse(is_valid)
        self.assertIn("resolution", err.lower())

    def test_local_vision_validator_fallback(self):
        jpeg_bytes = create_dummy_jpeg_bytes(color=(120, 120, 120))
        result = ai_service.analyze_animal_photo(jpeg_bytes, rekognition_client=None)
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['model_name'], 'PawPatrol-Local-Vision-Validator-v1')
        self.assertTrue(result['requires_human_confirmation'])
        self.assertIn('clinical_disclaimer', result)

    def test_rekognition_detect_labels_mock(self):
        """Mocks AWS Rekognition detect_labels returning Dog labels."""
        mock_rekognition = MagicMock()
        mock_rekognition.detect_labels.return_value = {
            'Labels': [
                {'Name': 'Dog', 'Confidence': 97.5, 'Parents': [{'Name': 'Canine'}, {'Name': 'Mammal'}]},
                {'Name': 'Canine', 'Confidence': 97.5, 'Parents': [{'Name': 'Mammal'}]},
                {'Name': 'Pet', 'Confidence': 90.0, 'Parents': []}
            ]
        }
        jpeg_bytes = create_dummy_jpeg_bytes()
        result = ai_service.analyze_animal_photo(jpeg_bytes, rekognition_client=mock_rekognition)
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['identified_species'], 'Dog')
        self.assertEqual(result['species_confidence'], 97.5)
        self.assertFalse(result['uncertainty_flag'])
        self.assertEqual(result['model_name'], 'AWS-Rekognition-DetectLabels-v2')

    def test_rekognition_low_confidence_triggers_uncertainty(self):
        """Low confidence detection (<70%) flags uncertainty."""
        mock_rekognition = MagicMock()
        mock_rekognition.detect_labels.return_value = {
            'Labels': [
                {'Name': 'Dog', 'Confidence': 58.2, 'Parents': []}
            ]
        }
        jpeg_bytes = create_dummy_jpeg_bytes()
        result = ai_service.analyze_animal_photo(jpeg_bytes, rekognition_client=mock_rekognition)
        self.assertTrue(result['uncertainty_flag'])

    def test_rekognition_failure_falls_back_gracefully(self):
        """If AWS Rekognition raises an exception, falls back to local vision without crashing."""
        mock_rekognition = MagicMock()
        mock_rekognition.detect_labels.side_effect = Exception("AWS Service Unavailable 503")
        jpeg_bytes = create_dummy_jpeg_bytes()
        result = ai_service.analyze_animal_photo(jpeg_bytes, rekognition_client=mock_rekognition)
        self.assertIn(result['status'], ['SUCCESS', 'LOW_CONFIDENCE'])
        self.assertEqual(result['model_name'], 'PawPatrol-Local-Vision-Validator-v1')


class TestLambdaProductionHandlers(unittest.TestCase):
    """Verifies production AWS Lambda handler logic with mocked AWS services."""

    def setUp(self):
        self.mock_table = MagicMock()
        self.mock_s3 = MagicMock()
        self.mock_sns = MagicMock()
        self.mock_rekognition = MagicMock()

        self.orig_table = lambda_function.table
        self.orig_s3 = lambda_function.s3_client
        self.orig_sns = lambda_function.sns_client
        self.orig_rekognition = lambda_function.rekognition_client

        lambda_function.table = self.mock_table
        lambda_function.s3_client = self.mock_s3
        lambda_function.sns_client = self.mock_sns
        lambda_function.rekognition_client = self.mock_rekognition
        lambda_function.S3_BUCKET_NAME = 'pawpatrol-photos-test'
        lambda_function.SNS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:123456789012:PawPatrol-Alerts'

    def tearDown(self):
        lambda_function.table = self.orig_table
        lambda_function.s3_client = self.orig_s3
        lambda_function.sns_client = self.orig_sns
        lambda_function.rekognition_client = self.orig_rekognition

    def test_create_report_success_and_no_base64_in_dynamodb(self):
        """Verifies report creation saves to DynamoDB and excludes base64 blobs."""
        payload = {
            'animal_type': 'Cat',
            'location_address': 'Block C Park, Pune',
            'description': 'Kitten with injured paw',
            'condition': 'MODERATE_INJURY',
            'symptoms': ['broken_bone'],
            'photo_s3_key': 'uploads/abc123.jpg',
            'photo_url': 'https://pawpatrol-photos-test.s3.ap-south-1.amazonaws.com/uploads/abc123.jpg',
            'reporter_name': 'Meera Patel',
            'reporter_phone': '+91 9822001122'
        }
        resp = lambda_function.handle_create_report(payload)
        self.assertEqual(resp['statusCode'], 201)
        body = json.loads(resp['body'])
        report = body['report']

        self.assertEqual(report['animal_type'], 'Cat')
        self.assertEqual(report['photo_s3_key'], 'uploads/abc123.jpg')
        self.assertNotIn('photo_data', report, "Base64 data must not be stored in DynamoDB")
        self.mock_table.put_item.assert_called_once()

    def test_create_report_missing_fields(self):
        """Missing required fields returns 400 Bad Request."""
        resp = lambda_function.handle_create_report({'animal_type': 'Dog'})
        self.assertEqual(resp['statusCode'], 400)
        body = json.loads(resp['body'])
        self.assertIn('Missing required fields', body['error'])

    def test_create_report_sns_resilience(self):
        """If SNS publish fails, report is still saved to DynamoDB and returns 201."""
        self.mock_sns.publish.side_effect = Exception("SNS Throttling")
        payload = {
            'animal_type': 'Dog',
            'location_address': 'Main Market Road',
            'description': 'Hit by car, heavy bleeding',
            'condition': 'CRITICAL_INJURY',
            'symptoms': ['bleeding_heavily', 'hit_by_vehicle']
        }
        resp = lambda_function.handle_create_report(payload)
        self.assertEqual(resp['statusCode'], 201)
        self.mock_table.put_item.assert_called_once()

    def test_get_reports_privacy_masking_and_s3_urls(self):
        """Public list view masks phone numbers and refreshes presigned S3 URLs."""
        self.mock_table.scan.return_value = {
            'Items': [
                {
                    'report_id': 'PAW-20261021-0001',
                    'animal_type': 'Dog',
                    'reporter_phone': '+91 9876543210',
                    'photo_s3_key': 'uploads/dog1.jpg',
                    'created_at': '2026-10-21T10:00:00Z',
                    'risk_level': 'HIGH',
                    'status': 'REPORTED'
                }
            ]
        }
        self.mock_s3.generate_presigned_url.return_value = 'https://s3.signed.url/dog1.jpg'

        resp = lambda_function.handle_get_reports({})
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        reports = body['reports']
        self.assertEqual(len(reports), 1)

        rep = reports[0]
        self.assertEqual(rep['reporter_phone_masked'], '+91****210')
        self.assertEqual(rep['photo_url'], 'https://s3.signed.url/dog1.jpg')

    def test_update_status_success(self):
        """Updating status to DISPATCHED returns updated attributes."""
        self.mock_table.update_item.return_value = {
            'Attributes': {
                'report_id': 'PAW-20261021-0001',
                'status': 'DISPATCHED',
                'updated_at': '2026-10-21T12:00:00Z'
            }
        }
        resp = lambda_function.handle_update_status('PAW-20261021-0001', {'status': 'DISPATCHED'})
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['report']['status'], 'DISPATCHED')

    def test_update_status_invalid_value(self):
        """Invalid status returns 400 Bad Request."""
        resp = lambda_function.handle_update_status('PAW-20261021-0001', {'status': 'INVALID_STATUS'})
        self.assertEqual(resp['statusCode'], 400)

    def test_generate_upload_url_mime_validation(self):
        """Valid image MIME types generate presigned URLs; invalid types are rejected."""
        self.mock_s3.generate_presigned_url.return_value = 'https://s3.upload.presigned.url'

        # Valid JPEG
        resp_valid = lambda_function.handle_generate_upload_url({'content_type': 'image/jpeg'})
        self.assertEqual(resp_valid['statusCode'], 200)
        body = json.loads(resp_valid['body'])
        self.assertIn('upload_url', body)
        self.assertEqual(body['expires_in'], 900)

        # Invalid PDF
        resp_invalid = lambda_function.handle_generate_upload_url({'content_type': 'application/pdf'})
        self.assertEqual(resp_invalid['statusCode'], 400)
        self.assertIn('Unsupported image content_type', json.loads(resp_invalid['body'])['error'])

    def test_analyze_photo_endpoint(self):
        """POST /analyze-photo parses base64, runs analysis, and returns structured result."""
        import base64
        jpeg_bytes = create_dummy_jpeg_bytes()
        b64_str = base64.b64encode(jpeg_bytes).decode('utf-8')

        resp = lambda_function.handle_analyze_photo({'image_base64': f"data:image/jpeg;base64,{b64_str}"})
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertTrue(body['success'])
        self.assertIn('analysis', body)
        self.assertIn('status', body['analysis'])

    def test_lambda_handler_routing(self):
        """Verifies full HTTP event routing through lambda_handler."""
        # 1. OPTIONS CORS Preflight
        event_options = {'requestContext': {'http': {'method': 'OPTIONS'}}, 'rawPath': '/reports'}
        resp_opt = lambda_function.lambda_handler(event_options, None)
        self.assertEqual(resp_opt['statusCode'], 200)

        # 2. GET /reports
        self.mock_table.scan.return_value = {'Items': []}
        event_get = {'requestContext': {'http': {'method': 'GET'}}, 'rawPath': '/reports'}
        resp_get = lambda_function.lambda_handler(event_get, None)
        self.assertEqual(resp_get['statusCode'], 200)


if __name__ == '__main__':
    unittest.main()
