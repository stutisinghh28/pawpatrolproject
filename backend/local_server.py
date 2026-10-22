"""
PawPatrol Local Development & Testing Server
Runs on standard Python 3.14 without requiring external dependencies or AWS credentials.
Serves frontend static assets at http://localhost:8000/ and handles REST API routes.
Supports local photo uploads, AI photo analysis, and persistent JSON storage.
"""

import os
import sys
import json
import time
import uuid
import base64
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = 8000
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'local_reports.json')
UPLOADS_DIR = os.path.join(DATA_DIR, 'uploads')

os.makedirs(UPLOADS_DIR, exist_ok=True)

# Import AI service
try:
    from ai_service import analyze_animal_photo, validate_image_bytes, DISCLAIMER_TEXT
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ai_service import analyze_animal_photo, validate_image_bytes, DISCLAIMER_TEXT

def seed_sample_reports():
    """Seeds realistic sample reports with AI metadata and triage scores."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if existing:
                    return existing
        except Exception:
            pass

    samples = [
        {
            "report_id": "PAW-20261020-A101",
            "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 1200)),
            "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600)),
            "status": "DISPATCHED",
            "animal_type": "Dog",
            "animal_age": "adult",
            "condition": "CRITICAL_INJURY",
            "symptoms": ["hit_by_vehicle", "bleeding_heavily", "broken_bone"],
            "is_trapped": False,
            "description": "Golden street dog struck by speeding car near main market crossing. Severe leg injury and visible bleeding. Rescue vehicle en route.",
            "location_address": "Near Central Market Metro Station Gate 2",
            "latitude": 28.6219,
            "longitude": 77.2150,
            "reporter_name": "Aarav Sharma",
            "reporter_phone": "+91 9811022334",
            "risk_level": "CRITICAL",
            "risk_score": 19,
            "risk_reasons": ["Severe trauma / life-threatening injury", "Active heavy bleeding", "Hit-by-vehicle trauma", "Suspected fractured limb"],
            "photo_url": None,
            "photo_s3_key": None,
            "ai_analysis": {
                "status": "SUCCESS",
                "model_name": "AWS-Rekognition-DetectLabels-v2",
                "identified_species": "Dog",
                "species_confidence": 98.4,
                "uncertainty_flag": False,
                "detected_labels": [
                    {"label": "Dog", "confidence": 98.4, "category": "Species"},
                    {"label": "Canine", "confidence": 98.4, "category": "AnimalFeature"}
                ],
                "clinical_disclaimer": DISCLAIMER_TEXT
            },
            "storage_tier": "LOCAL_SERVER"
        },
        {
            "report_id": "PAW-20261020-B202",
            "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 7200)),
            "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 3600)),
            "status": "IN_TREATMENT",
            "animal_type": "Cat",
            "animal_age": "infant",
            "condition": "MODERATE_INJURY",
            "symptoms": ["severe_malnutrition", "skin_mange"],
            "is_trapped": True,
            "description": "Young kitten stuck inside an uncovered roadside drainage pipe. Very weak, crying continuously.",
            "location_address": "Behind Community Hall, Sector 14",
            "latitude": 28.6350,
            "longitude": 77.2250,
            "reporter_name": "Priya Sen",
            "reporter_phone": "+91 9711554433",
            "risk_level": "HIGH",
            "risk_score": 11,
            "risk_reasons": ["Moderate injury or acute illness", "Severe malnutrition / dehydration", "Trapped in dangerous hazard", "Infant animal vulnerability"],
            "photo_url": None,
            "photo_s3_key": None,
            "ai_analysis": {
                "status": "SUCCESS",
                "model_name": "AWS-Rekognition-DetectLabels-v2",
                "identified_species": "Cat",
                "species_confidence": 95.1,
                "uncertainty_flag": False,
                "detected_labels": [
                    {"label": "Cat", "confidence": 95.1, "category": "Species"},
                    {"label": "Kitten", "confidence": 92.0, "category": "AnimalFeature"}
                ],
                "clinical_disclaimer": DISCLAIMER_TEXT
            },
            "storage_tier": "LOCAL_SERVER"
        },
        {
            "report_id": "PAW-20261020-C303",
            "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 86400)),
            "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 18000)),
            "status": "RESCUED",
            "animal_type": "Cattle",
            "animal_age": "adult",
            "condition": "SKIN_OR_SICK",
            "symptoms": ["skin_mange"],
            "is_trapped": False,
            "description": "Cow with minor leg infection resting near temple park. Administered antibiotic spray and scheduled for sanctuary transfer.",
            "location_address": "Near Old Shiv Temple, Park Lane",
            "latitude": 28.6050,
            "longitude": 77.2350,
            "reporter_name": "Ramesh Kumar",
            "reporter_phone": "+91 9988776655",
            "risk_level": "MEDIUM",
            "risk_score": 4,
            "risk_reasons": ["Skin condition or chronic illness", "Severe skin mange"],
            "photo_url": None,
            "photo_s3_key": None,
            "ai_analysis": None,
            "storage_tier": "LOCAL_SERVER"
        }
    ]

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(samples, f, indent=2)
    return samples

def load_reports():
    if not os.path.exists(DATA_FILE):
        return seed_sample_reports()
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return seed_sample_reports()

def save_reports(reports):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(reports, f, indent=2)

def calculate_risk(condition, symptoms, is_trapped, animal_age):
    score = 0
    reasons = []

    condition_weights = {
        'CRITICAL_INJURY': (8, 'Severe trauma / life-threatening injury'),
        'MODERATE_INJURY': (4, 'Moderate injury or acute illness'),
        'SKIN_OR_SICK': (2, 'Skin condition or chronic illness'),
        'HEALTHY_STRAY': (1, 'Healthy stray routine check')
    }
    pts, reason = condition_weights.get(condition, (1, 'General report'))
    score += pts
    reasons.append(reason)

    symptoms_set = set(symptoms or [])
    if 'unconscious' in symptoms_set:
        score += 10
        reasons.append('Unconscious / unresponsive')
    if 'bleeding_heavily' in symptoms_set:
        score += 6
        reasons.append('Heavy active bleeding')
    if 'hit_by_vehicle' in symptoms_set:
        score += 5
        reasons.append('Hit-and-run impact')
    if 'broken_bone' in symptoms_set:
        score += 4
        reasons.append('Suspected fractured limb')
    if 'rabies_symptoms' in symptoms_set:
        score += 6
        reasons.append('Suspected neurological symptoms')
    if 'skin_mange' in symptoms_set:
        score += 2
        reasons.append('Severe skin mange')
    if 'severe_malnutrition' in symptoms_set:
        score += 3
        reasons.append('Severe malnutrition / dehydration')

    if is_trapped:
        score += 4
        reasons.append('Trapped in hazardous location')
    if animal_age == 'infant':
        score += 2
        reasons.append('Infant animal vulnerability')

    if score >= 12 or 'unconscious' in symptoms_set or ('bleeding_heavily' in symptoms_set and ('hit_by_vehicle' in symptoms_set or condition == 'CRITICAL_INJURY')):
        level = 'CRITICAL'
    elif score >= 7 or 'broken_bone' in symptoms_set or 'hit_by_vehicle' in symptoms_set:
        level = 'HIGH'
    elif score >= 4 or 'skin_mange' in symptoms_set or is_trapped:
        level = 'MEDIUM'
    else:
        level = 'LOW'

    return level, score, reasons

class PawPatrolHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Serve uploaded files from data/uploads
        if path.startswith('/uploads/'):
            filename = os.path.basename(path)
            file_path = os.path.join(UPLOADS_DIR, filename)
            if os.path.exists(file_path):
                self.send_response(200)
                if filename.endswith('.png'):
                    self.send_header('Content-Type', 'image/png')
                elif filename.endswith('.webp'):
                    self.send_header('Content-Type', 'image/webp')
                else:
                    self.send_header('Content-Type', 'image/jpeg')
                self._send_cors_headers()
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        if path == '/api/reports' or path == '/reports':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()

            query = urllib.parse.parse_qs(parsed.query)
            risk = query.get('risk_level', [None])[0]
            status = query.get('status', [None])[0]
            animal = query.get('animal_type', [None])[0]

            reports = load_reports()
            if risk and risk != 'ALL':
                reports = [r for r in reports if r.get('risk_level') == risk]
            if status and status != 'ALL':
                reports = [r for r in reports if r.get('status') == status]
            if animal and animal != 'ALL':
                reports = [r for r in reports if r.get('animal_type') == animal]

            self.wfile.write(json.dumps({'success': True, 'reports': reports, 'count': len(reports)}).encode('utf-8'))
            return

        elif path.startswith('/api/reports/') or path.startswith('/reports/'):
            report_id = path.rstrip('/').split('/')[-1]
            reports = load_reports()
            matching = [r for r in reports if r.get('report_id') == report_id]
            if matching:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'report': matching[0]}).encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Report not found'}).encode('utf-8'))
            return

        # Serve static frontend files
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(post_body) if post_body else {}
        except Exception:
            data = {}

        # 1. AI Photo Analysis Endpoint
        if path == '/api/analyze-photo' or path == '/analyze-photo':
            image_b64 = data.get('image_base64')
            if not image_b64:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing required field: image_base64'}).encode('utf-8'))
                return

            if ',' in image_b64:
                image_b64 = image_b64.split(',', 1)[1]

            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid base64 payload'}).encode('utf-8'))
                return

            analysis = analyze_animal_photo(image_bytes)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'analysis': analysis}).encode('utf-8'))
            return

        # 2. Local Photo Upload Endpoint (Replaces base64 in database)
        elif path == '/api/upload':
            filename = data.get('filename', f"{uuid.uuid4().hex}.jpg")
            image_b64 = data.get('image_base64')

            if not image_b64:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing image_base64'}).encode('utf-8'))
                return

            if ',' in image_b64:
                image_b64 = image_b64.split(',', 1)[1]

            try:
                image_bytes = base64.b64decode(image_b64)
                file_ext = os.path.splitext(filename)[1] or '.jpg'
                saved_filename = f"{uuid.uuid4().hex}{file_ext}"
                file_path = os.path.join(UPLOADS_DIR, saved_filename)
                with open(file_path, 'wb') as f:
                    f.write(image_bytes)

                public_url = f"http://localhost:{PORT}/uploads/{saved_filename}"

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'photo_url': public_url,
                    'photo_s3_key': f"uploads/{saved_filename}",
                    'size_bytes': len(image_bytes)
                }).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': f"Upload failed: {str(e)}"}).encode('utf-8'))
                return

        # 3. Create Rescue Report
        elif path == '/api/reports' or path == '/reports':
            animal_type = data.get('animal_type')
            address = data.get('location_address')
            desc = data.get('description')

            if not animal_type or not address or not desc:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing required fields'}).encode('utf-8'))
                return

            condition = data.get('condition', 'HEALTHY_STRAY')
            symptoms = data.get('symptoms', [])
            is_trapped = bool(data.get('is_trapped', False))
            animal_age = data.get('animal_age', 'adult')

            risk_level, score, reasons = calculate_risk(condition, symptoms, is_trapped, animal_age)

            ai_analysis = data.get('ai_analysis')
            species_mismatch = False
            if ai_analysis and isinstance(ai_analysis, dict):
                ai_species = ai_analysis.get('identified_species')
                ai_conf = ai_analysis.get('species_confidence', 0.0)
                if ai_species and ai_conf >= 80.0 and ai_species.lower() != str(animal_type).lower():
                    species_mismatch = True
                    reasons.append(f"AI Observation: Identified as {ai_species} ({ai_conf}% conf)")

            date_str = time.strftime('%Y%m%d')
            rand_str = uuid.uuid4().hex[:5].upper()
            report_id = f"PAW-{date_str}-{rand_str}"
            now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

            new_report = {
                'report_id': report_id,
                'created_at': now_iso,
                'updated_at': now_iso,
                'status': 'REPORTED',
                'animal_type': animal_type,
                'animal_age': animal_age,
                'condition': condition,
                'symptoms': symptoms,
                'is_trapped': is_trapped,
                'description': desc,
                'location_address': address,
                'latitude': data.get('latitude'),
                'longitude': data.get('longitude'),
                'reporter_name': data.get('reporter_name', 'Anonymous Citizen'),
                'reporter_phone': data.get('reporter_phone', ''),
                'risk_level': risk_level,
                'risk_score': score,
                'risk_reasons': reasons,
                'species_mismatch': species_mismatch,
                'photo_url': data.get('photo_url'),
                'photo_s3_key': data.get('photo_s3_key'),
                'ai_analysis': ai_analysis,
                'storage_tier': 'LOCAL_SERVER'
            }

            reports = load_reports()
            reports.insert(0, new_report)
            save_reports(reports)

            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'report': new_report}).encode('utf-8'))
            return

        elif path == '/api/upload-url' or path == '/upload-url':
            filename = data.get('filename', 'upload.jpg')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                'upload_url': f"http://localhost:{PORT}/api/upload",
                'key': f"uploads/{filename}",
                'expires_in': 900
            }).encode('utf-8'))
            return

        self.send_response(404)
        self._send_cors_headers()
        self.end_headers()

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/reports/') or path.startswith('/reports/'):
            report_id = path.rstrip('/').split('/')[-1]
            content_length = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_length).decode('utf-8')
            try:
                updates = json.loads(post_body) if post_body else {}
            except Exception:
                updates = {}

            reports = load_reports()
            found = False
            updated_report = None
            for r in reports:
                if r.get('report_id') == report_id:
                    if 'status' in updates:
                        r['status'] = updates['status']
                    r['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    updated_report = r
                    found = True
                    break

            if found:
                save_reports(reports)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'report': updated_report}).encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Report not found'}).encode('utf-8'))
            return

        self.send_response(404)
        self._send_cors_headers()
        self.end_headers()

def run():
    seed_sample_reports()
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, PawPatrolHandler)
    print("=" * 65)
    print("[PawPatrol] Local Development Server Running!")
    print(f">> Open in your web browser: http://localhost:{PORT}/")
    print(f">> REST API Endpoint:        http://localhost:{PORT}/api/reports")
    print(f">> AI Photo Analysis:       http://localhost:{PORT}/api/analyze-photo")
    print("Press Ctrl+C to stop the server.")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server gracefully...")
        httpd.server_close()

if __name__ == '__main__':
    run()
