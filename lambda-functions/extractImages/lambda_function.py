# wip - extract imges from pdf files and add save them to an S3 bucket

import boto3
import os
import io
import pdfplumber
import json
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

s3 = boto3.client('s3')

def validate_environment_variables():
    """
    Validate that all required environment variables are present.
    Raises ValueError with descriptive message if any are missing.
    """
    required_vars = ['PDF_STORAGE_BUCKET', 'IMAGE_STORAGE_BUCKET']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    return {
        'pdf_storage_bucket': os.environ.get('PDF_STORAGE_BUCKET'),
        'image_storage_bucket': os.environ.get('IMAGE_STORAGE_BUCKET'),
        'image_prefix': os.environ.get('IMAGE_PREFIX', 'extracted_images/')
    }

def lambda_handler(event, context):
    """
    Manually invoked Lambda function to process all PDF files in the specified S3 bucket,
    including all paths and subdirectories. Extracts images, stores them in a destination
    S3 bucket, and returns a list of JSON objects with S3 URIs and captions.

    Args:
        event (dict): Event data passed to the Lambda function (can be empty).
        context (object): Lambda context object.

    Returns:
        dict: A JSON string containing a list of JSON objects, each with 'image-ref' (S3 URI)
              and 'caption'.
    """
    try:
        # Validate environment variables at function startup
        env_vars = validate_environment_variables()
        logger.info("Environment variables validated successfully")
    except ValueError as e:
        logger.error(f"Environment validation failed: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Configuration error: {e}"})
        }
    
    source_bucket = env_vars['pdf_storage_bucket']
    destination_bucket = env_vars['image_storage_bucket']
    destination_prefix = env_vars['image_prefix']
    
    output_data = []

    try:
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=source_bucket)

        pdf_files = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].lower().endswith('.pdf'):
                        pdf_files.append(obj['Key'])

        logger.info(f"Found {len(pdf_files)} PDF files in s3://{source_bucket}: {pdf_files}")

        for pdf_key in pdf_files:
            logger.info(f"Processing: {pdf_key}")
            try:
                pdf_object = s3.get_object(Bucket=source_bucket, Key=pdf_key)
                pdf_bytes = io.BytesIO(pdf_object['Body'].read())

                with pdfplumber.open(pdf_bytes) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        for i, image in enumerate(page.images):
                            image_name = f"{os.path.splitext(os.path.basename(pdf_key))[0]}_page_{page_num + 1}_image_{i + 1}.{image['filetype'].lower()}"
                            image_bytes = image['content']
                            destination_key = f"{destination_prefix}{image_name}"

                            # Upload image to the destination S3 bucket
                            s3.put_object(Bucket=destination_bucket, Key=destination_key, Body=image_bytes)
                            s3_uri = f"s3://{destination_bucket}/{destination_key}"

                            # Extract nearby text for caption
                            image_bbox = (image['x0'], image['top'], image['x1'], image['bottom'])
                            nearby_text = []
                            for word in page.extract_words():
                                word_bbox = (word['x0'], word['top'], word['x1'], word['bottom'])
                                if max(image_bbox[0], word_bbox[0]) < min(image_bbox[2], word_bbox[2]) + 50 and \
                                   max(image_bbox[1], word_bbox[1]) < min(image_bbox[3], word_bbox[3]) + 50:
                                    nearby_text.append(word['text'])

                            caption = " ".join(nearby_text).strip()
                            if caption:
                                output_data.append({
                                    "image-ref": s3_uri,
                                    "caption": caption
                                })

            except Exception as e:
                logger.error(f"Error processing {pdf_key}: {e}")

    except Exception as e:
        logger.error(f"Error listing or processing S3 objects: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Error listing or processing S3 objects: {e}"})
        }

    return {
        'statusCode': 200,
        'body': json.dumps(output_data, indent=2)
    }