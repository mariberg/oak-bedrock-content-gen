# Deployment Scripts

This directory contains automation scripts for packaging and deploying the Oak Bedrock Content Gen infrastructure.

## Scripts

### package-functions.sh

Packages all Lambda functions with their dependencies into deployment-ready zip files.

**Usage:**
```bash
./scripts/package-functions.sh
```

**What it does:**
- Packages Node.js functions (oak-pdf-processor) with npm dependencies
- Packages Python functions (describeQuiz, createNewImage, extractImages) with pip dependencies
- Creates unique package names with timestamps
- Generates a package manifest JSON file for deployment tracking

**Output:**
- Creates `deployment-packages/` directory
- Generates zip files for each Lambda function
- Creates `package-manifest-{timestamp}.json` with package information

### deploy.sh

Uploads packaged Lambda functions to S3 and deploys/updates the CloudFormation stack.

**Usage:**
```bash
# Deploy with defaults
./scripts/deploy.sh

# Custom stack name and region
./scripts/deploy.sh -s my-stack -r us-west-2

# Use specific package timestamp
./scripts/deploy.sh -t 20240107-143022

# Use custom parameters file
./scripts/deploy.sh -p dev-parameters.json
```

**Options:**
- `-s, --stack-name NAME`: CloudFormation stack name (default: oak-content-gen)
- `-r, --region REGION`: AWS region (default: us-east-1)
- `-p, --parameters FILE`: Parameters file path (default: ./parameters.json)
- `-t, --timestamp TIMESTAMP`: Use specific package timestamp
- `-h, --help`: Show help message

**What it does:**
- Creates S3 code bucket if it doesn't exist
- Uploads Lambda packages to S3
- Deploys or updates CloudFormation stack
- Handles deployment failures with rollback options
- Outputs deployment results and resource information

## Prerequisites

### For package-functions.sh:
- Node.js and npm (for Node.js functions)
- Python 3 and pip3 (for Python functions)
- zip command

### For deploy.sh:
- AWS CLI configured with appropriate credentials
- CloudFormation template at `cloudformation/infrastructure.yaml`
- Parameters file (default: `parameters.json`)
- **OAK_API_KEY environment variable** - Your Oak Academy API key

## Workflow

1. **Set your Oak Academy API key:**
   ```bash
   export OAK_API_KEY="your-actual-api-key-here"
   ```

2. **Package functions:**
   ```bash
   ./scripts/package-functions.sh
   ```

3. **Deploy to AWS:**
   ```bash
   ./scripts/deploy.sh
   ```

4. **Deploy to different environment:**
   ```bash
   export OAK_API_KEY="your-api-key"
   ./scripts/deploy.sh -s oak-content-gen-prod -r us-west-2 -p prod-parameters.json
   ```

## Security Note

The Oak Academy API key is now managed via the `OAK_API_KEY` environment variable for security. Never commit API keys to version control. The `parameters.json.example` file shows the expected parameter structure without sensitive values.

## Error Handling

Both scripts include comprehensive error handling:
- Prerequisites checking
- Clear error messages
- Rollback options for failed deployments
- Detailed logging with color-coded output

## Output Files

- `deployment-packages/`: Contains packaged Lambda functions
- `package-manifest-{timestamp}.json`: Package tracking information
- `deployment-info-{timestamp}.json`: Deployment results and resource information