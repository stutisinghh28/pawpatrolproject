# PawPatrol - Step-by-Step AWS Deployment & AI Configuration Guide

This guide is designed for beginners using Windows and the **AWS Management Console (Visual Web Interface)**. Follow these steps carefully with your team.

---

## 1. Pre-Deployment Architecture & Cost Breakdown

| Component | AWS Resource Name | Purpose | Monthly Cost (Free Tier) |
| :--- | :--- | :--- | :--- |
| **Database** | `PawPatrol-Reports` | Stores rescue reports & AI metadata | **$0.00** (25 GB always free) |
| **Backend Compute** | `PawPatrol-Backend` | Python 3.14 x86_64 Lambda API | **$0.00** (1M requests free/mo) |
| **API Gateway / URL**| Lambda Function URL | HTTPS endpoint with CORS | **$0.00** (Included with Lambda) |
| **Photo Storage** | `pawpatrol-photos-<id>` | Private S3 bucket for evidence | **$0.00** (5 GB free for 12 mo) |
| **Emergency Alerts** | `PawPatrol-Alerts` | Real-time email dispatch on Critical/High | **$0.00** (1,000 emails free/mo) |
| **Photo AI Analysis**| Amazon Rekognition | Detects species & visual context | **$0.00** (5,000 images free/mo) |

> [!NOTE]
> **Total Estimated Monthly Cost: $0.00** across all 3 team members during development and testing.

---

## 2. AI Model Architecture & Clinical Reality

PawPatrol integrates computer vision responsibly:

1. **Standard Computer Vision (Amazon Rekognition `DetectLabels`):**
   - **Supported:** Species recognition (Dog, Cat, Cattle, Bird), visual attributes (Canine, Kitten, Indoors, Outdoors, Street).
   - **Cost:** Free within 5,000 images/month.
   - **Limitation:** General-purpose object detection is **NOT** a clinical veterinary diagnosis. It cannot detect internal bleeding, bone fractures, rabies, or infections.

2. **Specialized Veterinary AI (Amazon Rekognition Custom Labels):**
   - **Supported:** Fine-grained classes such as `VISIBLE_LACERATION`, `SEVERE_MANGE_LESION`, `HEALTHY_COAT`.
   - **Prerequisites to Train:**
     - A labeled dataset of at least 50–200 annotated photos per medical class stored in an S3 bucket with a Ground Truth manifest.
     - Model training cost: ~$1.00/hour (~$2.00 total per training job).
     - Running endpoint cost: ~$4.00/hour per Inference Unit (must be stopped when not demoing to avoid charges).
   - **Integration:** The backend code checks `REKOGNITION_PROJECT_VERSION_ARN`. If present, it calls Custom Labels; otherwise, it defaults to standard Rekognition and local vision validation.

3. **Triage Safeguard:**
   - Rule-based triage remains the primary emergency safeguard.
   - AI uncertainty or low confidence **never downgrades** an urgent emergency report.

---

## 3. Step-by-Step AWS Management Console Deployment

### Step 1: Choose One Region Consistently
1. Log in to the [AWS Management Console](https://console.aws.amazon.com/).
2. Look at the top-right header next to your account name.
3. Select **Asia Pacific (Mumbai) `ap-south-1`** (or **US East (N. Virginia) `us-east-1`**).
4. **All resources below must be created in this exact same region.**

---

### Step 2: Create the DynamoDB Table
1. Search for **DynamoDB** in the top search bar and open the service.
2. Click **Create table**.
3. **Table name:** `PawPatrol-Reports` (Case-sensitive!).
4. **Partition key:** `report_id` (Type: `String`).
5. Under **Table settings**, select **Customize settings**.
6. Under **Read/write capacity settings**, select **On-demand** (Pay per request — ensures $0.00 when idle).
7. Scroll to the bottom and click **Create table**. Wait until Status is **Active**.

---

### Step 3: Create Private S3 Bucket for Photographs
1. Search for **S3** and open the service.
2. Click **Create bucket**.
3. **Bucket name:** `pawpatrol-photos-YOURNAME-2026` (Must be lowercase, unique).
4. **Region:** Same region as Step 1.
5. **Block Public Access settings:** Keep **Block *all* public access** CHECKED.
   *(Photos remain strictly private; viewing and uploading are performed via short-lived Pre-signed URLs).*
6. Click **Create bucket**.
7. Click on your new bucket name > click the **Permissions** tab.
8. Scroll down to **Cross-origin resource sharing (CORS)** > click **Edit**.
9. Paste:
```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
  }
]
```
10. Click **Save changes**.

---

### Step 4: Create Amazon SNS Alert Topic
1. Search for **SNS** and open **Simple Notification Service**.
2. Click **Topics** > **Create topic**.
3. **Type:** Select **Standard**.
4. **Name:** `PawPatrol-Alerts`.
5. Click **Create topic**.
6. Copy the **Topic ARN** (e.g. `arn:aws:sns:ap-south-1:123456789012:PawPatrol-Alerts`).
7. Under the **Subscriptions** tab, click **Create subscription**:
   - **Protocol:** Select `Email`.
   - **Endpoint:** Enter your email address.
   - Click **Create subscription**.
8. Open your email inbox and click **Confirm subscription** on the email from AWS.

---

### Step 5: Create IAM Execution Role
1. Search for **IAM** and open the service.
2. Click **Roles** > **Create role**.
3. **Trusted entity type:** Select **AWS service**.
4. **Use case:** Select **Lambda** > Click **Next**.
5. Click **Create policy** (opens in a new tab) > select the **JSON** tab:
6. Paste the contents of [`aws/lambda_policy.json`](file:///C:/Users/stuti/.gemini/antigravity/scratch/PawPatrol/aws/lambda_policy.json):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchLogging",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Sid": "DynamoDBReportAccess",
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Scan", "dynamodb:Query"],
      "Resource": "arn:aws:dynamodb:*:*:table/PawPatrol-Reports"
    },
    {
      "Sid": "S3PhotoUploadAccess",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::pawpatrol-photos-*/*"
    },
    {
      "Sid": "SNSEmergencyAlerts",
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": "arn:aws:sns:*:*:PawPatrol-Alerts"
    },
    {
      "Sid": "RekognitionPhotoAI",
      "Effect": "Allow",
      "Action": ["rekognition:DetectLabels", "rekognition:DetectCustomLabels"],
      "Resource": "*"
    }
  ]
}
```
7. Name the policy `PawPatrol-LeastPrivilege-Policy` and click **Create policy**.
8. Go back to the Role creation tab, refresh permissions, search and select:
   - `PawPatrol-LeastPrivilege-Policy`
9. Name the role `PawPatrol-Lambda-Role` and click **Create role**.

---

### Step 6: Deploy AWS Lambda Function
1. Search for **Lambda** and click **Create function**.
2. Select **Author from scratch**.
3. **Function name:** `PawPatrol-Backend`.
4. **Runtime:** **Python 3.14**.
5. **Architecture:** **x86_64**.
6. Under **Change default execution role**, choose **Use an existing role** > select `PawPatrol-Lambda-Role`.
7. Click **Create function**.

#### Upload Code:
1. In the **Code source** editor:
   - Copy the entire contents of [`backend/lambda_function.py`](file:///C:/Users/stuti/.gemini/antigravity/scratch/PawPatrol/backend/lambda_function.py).
   - Paste it into `lambda_function.py` in the console editor.
   - Click the orange **Deploy** button.

#### Set Environment Variables:
1. Go to **Configuration** tab > **Environment variables** > **Edit**:
   - `DYNAMODB_TABLE`: `PawPatrol-Reports`
   - `S3_BUCKET`: `pawpatrol-photos-YOURNAME-2026` (your bucket name)
   - `SNS_TOPIC_ARN`: `arn:aws:sns:...:PawPatrol-Alerts` (from Step 4)
   - `AWS_REGION`: `ap-south-1`
2. Click **Save**.

#### Enable Lambda Function URL (Public HTTPS API):
1. In the **Configuration** tab, click **Function URL** in the left menu.
2. Click **Create function URL**.
3. **Auth type:** Select **NONE** (Allows web browser access).
4. Check **Configure cross-origin resource sharing (CORS)**:
   - **Allow origin:** `*`
   - **Allow headers:** `*`
   - **Allow methods:** `GET`, `POST`, `PATCH`, `OPTIONS`
5. Click **Save**.
6. Copy the generated **Function URL** (e.g. `https://xxxx.lambda-url.ap-south-1.on.aws/`).

---

### Step 7: Connect Frontend & Verify Deployment
1. Open `http://localhost:8000/` or open `frontend/index.html` in your web browser.
2. Click the **API Status Pill (⚙️)** in the top right.
3. Select **AWS Cloud Mode**.
4. Paste your **Lambda Function URL** into the input field.
5. Click **Save & Connect**.
6. The status dot will turn blue with **AWS Cloud Connected**.
7. Attach a photo, review the AI species identification card, confirm symptoms, and submit the report!
8. Check your email for the emergency alert and view the item in your DynamoDB table.
