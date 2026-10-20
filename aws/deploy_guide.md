# PawPatrol - Step-by-Step AWS Deployment Guide

This guide is designed for beginners using Windows and PowerShell. Follow either the **AWS Management Console (Visual)** or **PowerShell / AWS CLI** route.

---

## Pre-Deployment Checklist
- **AWS Account:** Active, brand-new Free Tier account.
- **Recommended Region:** `ap-south-1` (Asia Pacific - Mumbai) or `us-east-1` (US East - N. Virginia). Keep all resources in the same region!
- **Estimated Cost:** **$0.00** (100% within AWS Free Tier limits):
  - DynamoDB: 25 GB storage and 25 RCU/WCU always free.
  - AWS Lambda: 1 Million free requests and 3.2M seconds of compute time per month.
  - S3: 5 GB standard storage free for 12 months.
  - SNS: 1 Million free publishes and 1,000 free email deliveries per month.

---

## Route A: AWS Management Console (Recommended for Beginners)

### Step 1: Create the DynamoDB Table
1. Open the [Amazon DynamoDB Console](https://console.aws.amazon.com/dynamodbv2/).
2. Confirm your region in the top-right header (e.g., `ap-south-1`).
3. Click **Create table**.
4. Configure table details:
   - **Table name:** `PawPatrol-Reports`
   - **Partition key:** `report_id` (Type: `String`)
5. Under **Table settings**, select **Customize settings**.
6. Under **Read/write capacity settings**, select **On-demand** (Pay per request — ensures zero charges while idle).
7. Scroll to the bottom and click **Create table**.
8. Wait ~30 seconds until the status displays **Active**.

---

### Step 2: Create S3 Photo Storage Bucket
1. Open the [Amazon S3 Console](https://s3.console.aws.amazon.com/s3/).
2. Click **Create bucket**.
3. **Bucket name:** `pawpatrol-photos-YOURNAME-2026` (Must be globally unique, lowercase, no spaces).
4. **AWS Region:** Same region as DynamoDB (e.g., `ap-south-1`).
5. **Block Public Access settings:** Keep **Block *all* public access** CHECKED (Do not make the bucket public; photos are uploaded securely using Pre-signed URLs).
6. Click **Create bucket**.
7. Click on your newly created bucket name > click the **Permissions** tab.
8. Scroll down to **Cross-origin resource sharing (CORS)** > click **Edit**.
9. Paste the following JSON and click **Save changes**:
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

---

### Step 3: Create Amazon SNS Alert Topic
1. Open the [Amazon SNS Console](https://console.aws.amazon.com/sns/v3/).
2. In the left sidebar, click **Topics** > click **Create topic**.
3. **Type:** Select **Standard**.
4. **Name:** `PawPatrol-Alerts`.
5. Click **Create topic**.
6. Copy the **Topic ARN** (e.g., `arn:aws:sns:ap-south-1:123456789012:PawPatrol-Alerts`).
7. Scroll down to the **Subscriptions** tab > click **Create subscription**:
   - **Protocol:** Select `Email`.
   - **Endpoint:** Enter your personal email address.
   - Click **Create subscription**.
8. Check your email inbox for an email from **AWS Notifications** with the subject *AWS Notification - Subscription Confirmation* and click **Confirm subscription**.

---

### Step 4: Create IAM Role for Lambda
1. Open the [IAM Console](https://console.aws.amazon.com/iamv2/).
2. In the left sidebar, click **Roles** > click **Create role**.
3. **Trusted entity type:** Select **AWS service**.
4. **Use case:** Select **Lambda** > Click **Next**.
5. Under **Add permissions**, search and select:
   - `AWSLambdaBasicExecutionRole`
   - `AmazonDynamoDBFullAccess` (or create a custom policy using `aws/lambda_policy.json`)
   - `AmazonSNSFullAccess`
   - `AmazonS3FullAccess`
6. Click **Next**.
7. **Role name:** `PawPatrol-Lambda-Role`.
8. Click **Create role**.

---

### Step 5: Deploy the AWS Lambda Backend Function
1. Open the [AWS Lambda Console](https://console.aws.amazon.com/lambda/).
2. Click **Create function**.
3. Select **Author from scratch**.
4. **Function name:** `PawPatrol-Backend`.
5. **Runtime:** Select **Python 3.14**.
6. **Architecture:** Select **x86_64**.
7. Under **Change default execution role**, choose **Use an existing role** and select `PawPatrol-Lambda-Role`.
8. Click **Create function**.

#### Upload the Code:
1. In the **Code source** editor:
   - Open `lambda_function.py`.
   - Replace the default code with the contents of `backend/lambda_function.py`.
   - Click **Deploy** (orange button).

#### Set Environment Variables:
1. Go to the **Configuration** tab > click **Environment variables** > click **Edit**.
2. Add the following key-value pairs:
   - `DYNAMODB_TABLE`: `PawPatrol-Reports`
   - `S3_BUCKET`: `pawpatrol-photos-YOURNAME-2026` (your bucket name from Step 2)
   - `SNS_TOPIC_ARN`: `arn:aws:sns:...:PawPatrol-Alerts` (from Step 3)
   - `AWS_REGION`: `ap-south-1`
3. Click **Save**.

#### Enable Lambda Function URL (Instant HTTPS Endpoint):
1. In the **Configuration** tab, click **Function URL** in the left menu.
2. Click **Create function URL**.
3. **Auth type:** Select **NONE** (Allows public web browser calls to the rescue reporting endpoint).
4. Expand **Additional settings** > Check **Configure cross-origin resource sharing (CORS)**:
   - **Allow origin:** `*`
   - **Allow headers:** `*`
   - **Allow methods:** Check `GET`, `POST`, `PATCH`, `OPTIONS`.
5. Click **Save**.
6. Copy the generated **Function URL** (e.g., `https://abcdefg12345.lambda-url.ap-south-1.on.aws/`).

---

### Step 6: Connect Frontend to Deployed AWS API
1. Open `http://localhost:8000` (or `frontend/index.html` in your browser).
2. Click the **API Status Pill** (top-right header with gear icon ⚙️).
3. Paste your AWS Lambda Function URL into the input field.
4. Click **Save & Connect**.
5. The status pill will turn blue with **AWS Cloud Connected**!
6. Submit a test report and observe it persist directly into your AWS DynamoDB table in real time!
