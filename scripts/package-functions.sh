#!/bin/bash

# Lambda Function Packaging Script
# Packages Node.js and Python Lambda functions with their dependencies
# Generates unique deployment package names with timestamps

set -e  # Exit on any error

# Configuration
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
PACKAGES_DIR="./deployment-packages"
LAMBDA_FUNCTIONS_DIR="./lambda-functions"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Create packages directory
log_info "Creating deployment packages directory..."
mkdir -p "$PACKAGES_DIR"

# Function to package Node.js Lambda function
package_nodejs_function() {
    local function_name=$1
    local function_dir="$LAMBDA_FUNCTIONS_DIR/$function_name"
    local package_name="${function_name}-${TIMESTAMP}.zip"
    local temp_dir=$(mktemp -d)
    
    log_info "Packaging Node.js function: $function_name"
    
    if [ ! -d "$function_dir" ]; then
        log_error "Function directory not found: $function_dir"
        return 1
    fi
    
    # Copy function code to temp directory
    cp -r "$function_dir"/* "$temp_dir/"
    
    # Install dependencies if package.json exists
    if [ -f "$temp_dir/package.json" ]; then
        log_info "Installing Node.js dependencies for $function_name"
        cd "$temp_dir"
        npm install --production --no-package-lock >/dev/null 2>&1
        cd - > /dev/null
    fi
    
    # Create zip package
    log_info "Creating zip package: $package_name"
    cd "$temp_dir"
    zip -r "$OLDPWD/$PACKAGES_DIR/$package_name" . -x "*.DS_Store*" "*.git*" >/dev/null 2>&1
    cd - > /dev/null
    
    # Cleanup temp directory
    rm -rf "$temp_dir"
    
    log_info "Successfully packaged $function_name -> $package_name"
}

# Function to package Python Lambda function
package_python_function() {
    local function_name=$1
    local function_dir="$LAMBDA_FUNCTIONS_DIR/$function_name"
    local package_name="${function_name}-${TIMESTAMP}.zip"
    local temp_dir=$(mktemp -d)
    
    log_info "Packaging Python function: $function_name"
    
    if [ ! -d "$function_dir" ]; then
        log_error "Function directory not found: $function_dir"
        return 1
    fi
    
    # Copy function code to temp directory
    cp -r "$function_dir"/* "$temp_dir/"
    
    # Install dependencies if requirements.txt exists
    if [ -f "$temp_dir/requirements.txt" ]; then
        log_info "Installing Python dependencies for $function_name"
        if command -v pip3 &> /dev/null; then
            pip3 install -r "$temp_dir/requirements.txt" -t "$temp_dir/" --no-deps >/dev/null 2>&1
        elif command -v python3 &> /dev/null; then
            python3 -m pip install -r "$temp_dir/requirements.txt" -t "$temp_dir/" --no-deps >/dev/null 2>&1
        else
            log_warn "No pip3 or python3 found, skipping dependency installation for $function_name"
        fi
    else
        log_warn "No requirements.txt found for $function_name, packaging without external dependencies"
    fi
    
    # Create zip package
    log_info "Creating zip package: $package_name"
    cd "$temp_dir"
    zip -r "$OLDPWD/$PACKAGES_DIR/$package_name" . -x "*.DS_Store*" "*.git*" "*__pycache__*" "*.pyc" >/dev/null 2>&1
    cd - > /dev/null
    
    # Cleanup temp directory
    rm -rf "$temp_dir"
    
    log_info "Successfully packaged $function_name -> $package_name"
}

# Main packaging logic
main() {
    log_info "Starting Lambda function packaging process..."
    log_info "Timestamp: $TIMESTAMP"
    
    # Package Node.js functions
    log_info "=== Packaging Node.js Functions ==="
    if [ -d "$LAMBDA_FUNCTIONS_DIR/oak-pdf-processor" ]; then
        package_nodejs_function "oak-pdf-processor"
        OAK_PDF_PROCESSOR_PACKAGE="oak-pdf-processor-${TIMESTAMP}.zip"
    else
        log_warn "oak-pdf-processor directory not found, skipping..."
    fi
    
    # Package Python functions
    log_info "=== Packaging Python Functions ==="
    
    # Array of Python function names
    PYTHON_FUNCTIONS=("describeQuiz" "createNewImage" "extractImages")
    
    for func in "${PYTHON_FUNCTIONS[@]}"; do
        if [ -d "$LAMBDA_FUNCTIONS_DIR/$func" ]; then
            case $func in
                "describeQuiz")
                    package_python_function "$func"
                    DESCRIBE_QUIZ_PACKAGE="describeQuiz-${TIMESTAMP}.zip"
                    ;;
                "createNewImage")
                    package_python_function "$func"
                    CREATE_NEW_IMAGE_PACKAGE="createNewImage-${TIMESTAMP}.zip"
                    ;;
                "extractImages")
                    package_python_function "$func"
                    EXTRACT_IMAGES_PACKAGE="extractImages-${TIMESTAMP}.zip"
                    ;;
            esac
        else
            log_warn "$func directory not found, skipping..."
        fi
    done
    
    # Generate package manifest
    log_info "=== Generating Package Manifest ==="
    MANIFEST_FILE="$PACKAGES_DIR/package-manifest-${TIMESTAMP}.json"
    
    cat > "$MANIFEST_FILE" << EOF
{
  "timestamp": "$TIMESTAMP",
  "packages": {
    "oak-pdf-processor": "${OAK_PDF_PROCESSOR_PACKAGE:-""}",
    "describeQuiz": "${DESCRIBE_QUIZ_PACKAGE:-""}",
    "createNewImage": "${CREATE_NEW_IMAGE_PACKAGE:-""}",
    "extractImages": "${EXTRACT_IMAGES_PACKAGE:-""}"
  }
}
EOF
    
    log_info "Package manifest created: $MANIFEST_FILE"
    
    # Summary
    log_info "=== Packaging Summary ==="
    log_info "Packages created in: $PACKAGES_DIR"
    ls -la "$PACKAGES_DIR"/*${TIMESTAMP}*
    
    log_info "Packaging completed successfully!"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if npm is available for Node.js functions
    if ! command -v npm &> /dev/null; then
        log_warn "npm not found - Node.js function packaging may fail"
    fi
    
    # Check if pip is available for Python functions
    if ! command -v pip3 &> /dev/null && ! command -v python3 &> /dev/null; then
        log_warn "pip3 or python3 not found - Python function packaging may fail"
    fi
    
    # Check if zip is available
    if ! command -v zip &> /dev/null; then
        log_error "zip command not found - required for packaging"
        exit 1
    fi
    
    log_info "Prerequisites check completed"
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_prerequisites
    main "$@"
fi