# AWS MCP Server Setup Guide for Windows

This guide explains how the official **AWS Model Context Protocol (MCP) Server** integrates with your AI assistant, and how to configure it safely on Windows.

---

## 1. Environment Compatibility Check

| Component | Status | Details |
| :--- | :--- | :--- |
| **Operating System** | Supported | Windows (PowerShell) |
| **Python** | Installed | Python 3.14.6 |
| **uv / uvx runner** | Installed | uv 0.11.21 (Recommended by AWS Labs) |
| **MCP Config Location** | Available | `C:\Users\stuti\.gemini\config\mcp_config.json` |
| **AWS Credentials** | Required | AWS access keys or IAM Identity Center profile |

---

## 2. Official AWS MCP Server

The official AWS MCP server collection is published by Amazon Web Services on GitHub at `awslabs/mcp` and distributed on PyPI.
The primary tool runner is:
```
awslabs.aws-api-mcp-server@latest
```
It communicates using the open Model Context Protocol over standard I/O (Stdio) and gives your AI pair programmer the ability to query resources, generate configurations, and inspect cloud resources.

---

## 3. Step-by-Step Configuration on Windows

### Step 3.1: Create an IAM Deployment User (Never use Root!)
1. Log in to the [AWS Management Console](https://console.aws.amazon.com/).
2. In the top search bar, type **IAM** and select **IAM**.
3. In the left navigation, click **Users** > **Create user**.
4. Set User name: `pawpatrol-dev`.
5. Under permissions, attach the needed development policies or attach the custom least-privilege policy provided in `aws/lambda_policy.json` plus `AWSLambda_FullAccess`, `AmazonDynamoDBFullAccess`.
6. After creating the user, go to the user's **Security credentials** tab.
7. Click **Create access key** > Choose **Command Line Interface (CLI)** > Download or copy the:
   - **Access Key ID**
   - **Secret Access Key**
   *(Keep these private! Never paste them into chat or commit them to Git.)*

### Step 3.2: Configure AWS Credentials on your Windows machine
In PowerShell:
```powershell
# Create .aws directory if it does not exist
New-Item -ItemType Directory -Path "$HOME\.aws" -Force

# Create credentials file
@"
[default]
aws_access_key_id = YOUR_ACCESS_KEY_ID
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
"@ | Out-File -FilePath "$HOME\.aws\credentials" -Encoding utf8

# Create config file setting your region (e.g., ap-south-1 Mumbai or us-east-1 N. Virginia)
@"
[default]
region = ap-south-1
output = json
"@ | Out-File -FilePath "$HOME\.aws\config" -Encoding utf8
```

### Step 3.3: Register AWS MCP in Antigravity Configuration
Add the server block to `C:\Users\stuti\.gemini\config\mcp_config.json`:

```json
{
  "mcpServers": {
    "awslabs.aws-api-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.aws-api-mcp-server@latest"
      ],
      "env": {
        "AWS_REGION": "ap-south-1",
        "AWS_PROFILE": "default",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

### Step 3.4: Restart the IDE / Session
Restart Antigravity or reopen the workspace. The Language Server will launch the MCP server via `uvx` and populate available AWS tools.
