# 🐾 PawPatrol - Stray Animal Rescue & Emergency Dispatch Platform

**PawPatrol** is a full-stack, cloud-native stray animal rescue reporting and emergency coordination web application built for college engineering capstone presentation.

It provides citizens with an instant, geo-enabled reporting portal that uses real computer vision to analyze animal photographs, automatically scores medical emergencies into rule-based triage risk tiers (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), dispatches real-time alerts via Amazon SNS, and persists all incident records in Amazon DynamoDB with private image storage in Amazon S3.

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Client["Frontend Client (Browser)"]
        UI["Web UI (HTML5 / CSS3 / Vanilla JS)"]
        Leaflet["Leaflet OpenStreetMap (GPS Geotagging)"]
        LiveRisk["Live Rule-Based Risk Engine"]
        AIAssist["AI Vision Review & Human Confirmation Card"]
    end

    subgraph AWS["AWS Serverless Cloud (Region: ap-south-1)"]
        FuncURL["Lambda Function URL (HTTPS Endpoint + CORS)"]
        Lambda["AWS Lambda Handler (Python 3.14 x86_64)"]
        Rekognition["Amazon Rekognition (Computer Vision AI)"]
        DDB[("Amazon DynamoDB (PawPatrol-Reports Table)")]
        S3[("Amazon S3 Bucket (Private Photos via Pre-signed URLs)")]
        SNS["Amazon SNS (PawPatrol-Alerts Topic)"]
    end

    subgraph Responders["Emergency Responders"]
        Email["Email / SMS Real-time Dispatches"]
    end

    UI -->|1. Analyze Photo Bytes| FuncURL
    FuncURL --> Lambda
    Lambda -->|2. Species & Visual Detection| Rekognition
    Rekognition -->|3. Labels, Confidence, Uncertainty| Lambda
    Lambda -->|4. Return AI Observation to User| UI
    UI -->|5. User Confirms/Corrects & Submits| FuncURL
    FuncURL --> Lambda
    Lambda -->|6. Request S3 Presigned PUT URL| S3
    UI -->|7. Upload Photo Directly to S3| S3
    Lambda -->|8. Authoritative Triage (AI never downgrades)| Lambda
    Lambda -->|9. Persist Report Data & AI Metadata (No base64)| DDB
    Lambda -->|10. If Urgent: Publish Dispatch Alert| SNS
    SNS --> Email
```

---

## 2. Computer Vision AI & Triage Safeguards

PawPatrol incorporates a responsible, multi-tier AI pipeline:

### A. Supported Capabilities
- **Animal Species Detection:** Identifies Dog, Cat, Cattle, Bird with confidence percentages (e.g. `Dog (97.5% confidence)`).
- **Scene & Attribute Detection:** Identifies outdoor environments, street context, postures.
- **Uncertainty & Species Conflict Detection:** If an image is blurry, dark, low-contrast, or if multiple species are detected, flags `uncertainty_flag = True`.
- **Human-in-the-Loop Review:** The user reviews AI predictions before submission, with a 1-click button to correct or confirm animal type.

### B. Clinical Reality & Disclaimers
General-purpose computer vision detects visual objects and species; it is **NOT** a substitute for clinical veterinary diagnosis. It cannot diagnose internal trauma, rabies, or viral infections. Custom fine-grained models (e.g., Amazon Rekognition Custom Labels) require trained datasets of verified animal injury images.

### C. Triage Safeguard
The rule-based triage matrix is strictly authoritative. **AI uncertainty or low confidence can NEVER downgrade an urgent emergency.**

---

## 3. Rule-Based Triage Matrix

| Triage Tier | Score Threshold | Key Clinical Indicators | SLA Target | Automated Action |
| :--- | :--- | :--- | :--- | :--- |
| 🚨 **CRITICAL** | Score &ge; 12 | Unconscious / unresponsive, heavy arterial bleeding, hit-and-run impact with severe trauma | &lt; 30 mins | Immediate SNS email dispatch to emergency veterinary squads |
| ⚠️ **HIGH** | Score 7 – 11 | Suspected limb fracture, rabies/neurological symptoms, trapped starving infant animals | &lt; 2 hours | Priority volunteer queue notification |
| 🩹 **MEDIUM** | Score 4 – 6 | Severe skin disease/mange, animal trapped in non-life-threatening ditch, open sores | &lt; 12 hours | Routine volunteer assessment visit |
| ✅ **LOW** | Score 1 – 3 | Healthy stray roaming safely, ABC (Animal Birth Control / Sterilization) request | &lt; 48 hours | Scheduled clinic checkup |

---

## 4. Project Directory Structure

```
PawPatrol/
├── .gitignore                   # Excludes credentials, venv, and local data
├── README.md                    # Project documentation & architecture
├── frontend/                    # Single-Page Web Application
│   ├── index.html               # Main application portal (Form, Dashboard, Map, SOPs)
│   ├── css/
│   │   └── style.css            # Responsive, emergency-ready modern CSS
│   └── js/
│       ├── app.js               # UI controller, live risk scoring, AI card integration
│       ├── api.js               # Unified API client (Cloud, Local Server, Explicit Offline)
│       └── map.js               # Leaflet OpenStreetMap interactive pin & markers
├── backend/                     # Serverless & Local Backend Services
│   ├── lambda_function.py       # Production AWS Lambda handler (Python 3.14 x86_64)
│   ├── ai_service.py            # AI Computer Vision service (Rekognition + Local Validator)
│   ├── local_server.py          # Windows local development server (http://localhost:8000)
│   ├── test_backend.py          # Comprehensive test suite (27 tests passing)
│   └── requirements.txt         # Dependencies (boto3, pillow)
├── aws/                         # AWS Infrastructure & Deployment Assets
│   ├── dynamodb_schema.json     # Table definition (Pay-Per-Request Free Tier)
│   ├── lambda_policy.json       # Least-privilege IAM policy (DynamoDB, S3, SNS, Rekognition)
│   ├── deploy_guide.md          # Step-by-step console and CLI deployment guide
│   └── mcp_setup.md             # AWS MCP Server configuration for Windows
└── data/                        # Local data directory for local server persistence
```





## 5. Local Quickstart (Windows & PowerShell)

### Step 1: Run Automated Test Suite
```powershell
python backend\test_backend.py
```
*Actual result: `Ran 27 tests in 0.085s ... OK` (verifying triage parity, AI photo analysis, Lambda handlers, S3 presigned URLs, and error resilience).*

### Step 2: Start Local Development Server
```powershell
python backend\local_server.py
```
*Open in your browser: `http://localhost:8000/`*

---

## 6. Security & Free Tier Compliance

- **Zero Root Credential Risk:** No AWS passwords or root credentials are used or stored.
- **Private S3 Storage:** Photos are stored privately; browser upload and view use short-lived Pre-signed URLs (15 minutes). No public bucket access.
- **No Base64 Bloat:** DynamoDB stores lightweight image S3 keys and metadata rather than megabytes of base64 strings.
- **Reporter Privacy:** Public list endpoints mask citizen phone numbers (e.g. `+91****210`).
- **100% Free Tier Eligible:**
  - DynamoDB: On-Demand (Free within 25 GB limit).
  - Lambda: 1 Million free invocations per month.
  - S3: 5 GB free tier storage.
  - SNS: 1,000 free email dispatches per month.
  - Rekognition: 5,000 free analyzed images per month.
