#!/bin/bash

# S3 Upload and CloudFormation Deployment Script
# Uploads packaged Lambda functions to S3 and deploys/updates CloudFormation stack

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PACKAGES_DIR="$PROJECT_ROOT/deployment-packages"
CLOUDFORMATION_DIR="$PROJECT_ROOT/cloudformation"
PARAMETERS_FILE="$PROJECT_ROOT/parameters.json"

# Default values
STACK_NAME="oak-content-gen"
AWS_REGION="us-east-1"
CODE_BUCKET_SUFFIX="code-storage"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy Oak Bedrock Content Gen infrastructure to AWS

OPTIONS:
    -s, --stack-name NAME       CloudFormation stack name (default: oak-content-gen)
    -r, --region REGION         AWS region (default: us-east-1)
    -p, --parameters FILE       Parameters file path (default: ./parameters.json)
    -t, --timestamp TIMESTAMP   Use specific package timestamp
    -h, --help                  Show this help message

EXAMPLES:
    $0                                          # Deploy with defaults
    $0 -s my-stack -r us-west-2               # Custom stack name and region
    $0 -t 20240107-143022                      # Use specific package timestamp
    $0 -p dev-parameters.json                  # Use custom parameters file

EOF
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--stack-name)
                STACK_NAME="$2"
                shift 2
                ;;
            -r|--region)
                AWS_REGION="$2"
                shift 2
                ;;
            -p|--parameters)
                PARAMETERS_FILE="$2"
                shift 2
                ;;
            -t|--timestamp)
                PACKAGE_TIMESTAMP="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found - required for deployment"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or invalid"
        exit 1
    fi
    
    # Check CloudFormation template
    if [ ! -f "$CLOUDFORMATION_DIR/infrastructure.yaml" ]; then
        log_error "CloudFormation template not found: $CLOUDFORMATION_DIR/infrastructure.yaml"
        exit 1
    fi
    
    # Check parameters file
    if [ ! -f "$PARAMETERS_FILE" ]; then
        log_error "Parameters file not found: $PARAMETERS_FILE"
        exit 1
    fi
    
    # Check for required environment variable
    if [ -z "$OAK_API_KEY" ]; then
        log_error "OAK_API_KEY environment variable is required but not set"
        log_info "Please set it with: export OAK_API_KEY=\"your-api-key-here\""
        exit 1
    fi
    
    log_info "Prerequisites check completed"
}

# Find latest package manifest or use specified timestamp
find_package_manifest() {
    if [ -n "$PACKAGE_TIMESTAMP" ]; then
        MANIFEST_FILE="$PACKAGES_DIR/package-manifest-${PACKAGE_TIMESTAMP}.json"
        if [ ! -f "$MANIFEST_FILE" ]; then
            log_error "Package manifest not found for timestamp: $PACKAGE_TIMESTAMP"
            exit 1
        fi
    else
        # Find the latest manifest file
        MANIFEST_FILE=$(ls -t "$PACKAGES_DIR"/package-manifest-*.json 2>/dev/null | head -n1)
        if [ -z "$MANIFEST_FILE" ]; then
            log_error "No package manifest found in $PACKAGES_DIR"
            log_info "Run './scripts/package-functions.sh' first to create deployment packages"
            exit 1
        fi
        PACKAGE_TIMESTAMP=$(basename "$MANIFEST_FILE" | sed 's/package-manifest-\(.*\)\.json/\1/')
    fi
    
    log_info "Using package manifest: $MANIFEST_FILE"
    log_info "Package timestamp: $PACKAGE_TIMESTAMP"
}

# Create or get S3 code bucket
setup_code_bucket() {
    CODE_BUCKET_NAME="${STACK_NAME}-${CODE_BUCKET_SUFFIX}"
    
    log_info "Setting up S3 code bucket: $CODE_BUCKET_NAME"
    
    # Check if bucket exists
    if aws s3api head-bucket --bucket "$CODE_BUCKET_NAME" --region "$AWS_REGION" 2>/dev/null; then
        log_info "S3 bucket already exists: $CODE_BUCKET_NAME"
    else
        log_info "Creating S3 bucket: $CODE_BUCKET_NAME"
        
        if [ "$AWS_REGION" = "us-east-1" ]; then
            aws s3api create-bucket --bucket "$CODE_BUCKET_NAME" --region "$AWS_REGION"
        else
            aws s3api create-bucket --bucket "$CODE_BUCKET_NAME" --region "$AWS_REGION" \
                --create-bucket-configuration LocationConstraint="$AWS_REGION"
        fi
        
        # Enable versioning
        aws s3api put-bucket-versioning --bucket "$CODE_BUCKET_NAME" \
            --versioning-configuration Status=Enabled
        
        # Block public access
        aws s3api put-public-access-block --bucket "$CODE_BUCKET_NAME" \
            --public-access-block-configuration \
            BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
        
        log_info "S3 bucket created and configured: $CODE_BUCKET_NAME"
    fi
}

# Upload Lambda packages to S3
upload_packages() {
    log_info "Uploading Lambda packages to S3..."
    
    # Read package manifest
    if ! PACKAGES=$(cat "$MANIFEST_FILE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for func, package in data['packages'].items():
    if package:
        print(f'{func}:{package}')
"); then
        log_error "Failed to parse package manifest"
        exit 1
    fi
    
    # Upload each package
    while IFS=':' read -r function_name package_name; do
        if [ -n "$package_name" ]; then
            local_path="$PACKAGES_DIR/$package_name"
            s3_key="packages/$package_name"
            
            if [ -f "$local_path" ]; then
                log_info "Uploading $function_name: $package_name"
                aws s3 cp "$local_path" "s3://$CODE_BUCKET_NAME/$s3_key" --region "$AWS_REGION"
                
                # Store S3 key for CloudFormation parameters
                case $function_name in
                    "oak-pdf-processor")
                        OAK_PDF_PROCESSOR_S3_KEY="$s3_key"
                        ;;
                    "describeQuiz")
                        DESCRIBE_QUIZ_S3_KEY="$s3_key"
                        ;;
                    "createNewImage")
                        CREATE_NEW_IMAGE_S3_KEY="$s3_key"
                        ;;
                    "extractImages")
                        EXTRACT_IMAGES_S3_KEY="$s3_key"
                        ;;
                esac
            else
                log_warn "Package file not found: $local_path"
            fi
        fi
    done <<< "$PACKAGES"
    
    log_info "Package upload completed"
}

# Deploy CloudFormation stack
deploy_stack() {
    log_info "Deploying CloudFormation stack: $STACK_NAME"
    
    # Prepare CloudFormation parameters
    CF_PARAMETERS=""
    
    # Add code bucket parameter
    CF_PARAMETERS="$CF_PARAMETERS ParameterKey=CodeStorageBucket,ParameterValue=$CODE_BUCKET_NAME"
    
    # Add API key from environment variable
    CF_PARAMETERS="$CF_PARAMETERS ParameterKey=OakApiKey,ParameterValue=$OAK_API_KEY"
    
    # Add S3 key parameters for each function
    [ -n "$OAK_PDF_PROCESSOR_S3_KEY" ] && CF_PARAMETERS="$CF_PARAMETERS ParameterKey=OakPdfProcessorPackageKey,ParameterValue=$OAK_PDF_PROCESSOR_S3_KEY"
    [ -n "$DESCRIBE_QUIZ_S3_KEY" ] && CF_PARAMETERS="$CF_PARAMETERS ParameterKey=DescribeQuizPackageKey,ParameterValue=$DESCRIBE_QUIZ_S3_KEY"
    [ -n "$CREATE_NEW_IMAGE_S3_KEY" ] && CF_PARAMETERS="$CF_PARAMETERS ParameterKey=CreateNewImagePackageKey,ParameterValue=$CREATE_NEW_IMAGE_S3_KEY"
    [ -n "$EXTRACT_IMAGES_S3_KEY" ] && CF_PARAMETERS="$CF_PARAMETERS ParameterKey=ExtractImagesPackageKey,ParameterValue=$EXTRACT_IMAGES_S3_KEY"
    
    # Read additional parameters from file
    if [ -f "$PARAMETERS_FILE" ]; then
        log_info "Loading parameters from: $PARAMETERS_FILE"
        ADDITIONAL_PARAMS=$(python3 -c "
import json, sys
with open('$PARAMETERS_FILE') as f:
    params = json.load(f)
    for key, value in params.items():
        print(f'ParameterKey={key},ParameterValue={value}', end=' ')
")
        CF_PARAMETERS="$CF_PARAMETERS $ADDITIONAL_PARAMS"
    fi
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_info "Stack exists, updating..."
        OPERATION="update-stack"
    else
        log_info "Stack does not exist, creating..."
        OPERATION="create-stack"
    fi
    
    # Deploy stack
    log_info "Executing CloudFormation $OPERATION..."
    
    aws cloudformation "$OPERATION" \
        --stack-name "$STACK_NAME" \
        --template-body "file://$CLOUDFORMATION_DIR/infrastructure.yaml" \
        --parameters $CF_PARAMETERS \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION"
    
    # Wait for deployment to complete
    log_info "Waiting for stack $OPERATION to complete..."
    
    if [ "$OPERATION" = "create-stack" ]; then
        aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"
    else
        aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"
    fi
    
    log_info "Stack $OPERATION completed successfully"
}

# Output deployment results
output_results() {
    log_info "=== Deployment Results ==="
    
    # Get stack outputs
    OUTPUTS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs' --output table 2>/dev/null || echo "No outputs available")
    
    echo "$OUTPUTS"
    
    # Get resource ARNs
    log_info "=== Resource Information ==="
    log_info "Stack Name: $STACK_NAME"
    log_info "Region: $AWS_REGION"
    log_info "Code Bucket: $CODE_BUCKET_NAME"
    log_info "Package Timestamp: $PACKAGE_TIMESTAMP"
    
    # Save deployment info
    DEPLOYMENT_INFO_FILE="$PROJECT_ROOT/deployment-info-${PACKAGE_TIMESTAMP}.json"
    cat > "$DEPLOYMENT_INFO_FILE" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "stackName": "$STACK_NAME",
  "region": "$AWS_REGION",
  "codeBucket": "$CODE_BUCKET_NAME",
  "packageTimestamp": "$PACKAGE_TIMESTAMP",
  "status": "deployed"
}
EOF
    
    log_info "Deployment info saved to: $DEPLOYMENT_INFO_FILE"
}

# Handle deployment failures
handle_failure() {
    log_error "Deployment failed!"
    
    # Get stack events for debugging
    log_info "Recent stack events:"
    aws cloudformation describe-stack-events --stack-name "$STACK_NAME" --region "$AWS_REGION" \
        --query 'StackEvents[0:10].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' \
        --output table 2>/dev/null || log_warn "Could not retrieve stack events"
    
    # Offer rollback option
    read -p "Do you want to rollback the stack? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rolling back stack..."
        aws cloudformation cancel-update-stack --stack-name "$STACK_NAME" --region "$AWS_REGION" 2>/dev/null || \
        aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$AWS_REGION"
    fi
    
    exit 1
}

# Main deployment function
main() {
    log_info "Starting Oak Bedrock Content Gen deployment..."
    log_info "Stack: $STACK_NAME, Region: $AWS_REGION"
    
    # Set up error handling
    trap handle_failure ERR
    
    check_prerequisites
    find_package_manifest
    setup_code_bucket
    upload_packages
    deploy_stack
    output_results
    
    log_info "Deployment completed successfully! 🎉"
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    parse_arguments "$@"
    main
fi