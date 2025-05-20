# wip - extract imges from pdf files and add save them to an S3 bucket

import boto3
import os
import io
import pdfplumber
import json

s3 = boto3.client('s3')
SOURCE_S3_BUCKET = 'oak-pdf-importer-pdf-storage'  # Replace with your source bucket name
DESTINATION_S3_BUCKET = 'oak-extracted-images'  # Replace with your destination bucket name
DESTINATION_S3_PREFIX = 'extracted_images/'  # Optional prefix for images in the destination bucket

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
    output_data = []

    try:
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=SOURCE_S3_BUCKET)

        pdf_files = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].lower().endswith('.pdf'):
                        pdf_files.append(obj['Key'])

        print(f"Found {len(pdf_files)} PDF files in s3://{SOURCE_S3_BUCKET}: {pdf_files}")

        for pdf_key in pdf_files:
            print(f"Processing: {pdf_key}")
            try:
                pdf_object = s3.get_object(Bucket=SOURCE_S3_BUCKET, Key=pdf_key)
                pdf_bytes = io.BytesIO(pdf_object['Body'].read())

                with pdfplumber.open(pdf_bytes) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        for i, image in enumerate(page.images):
                            image_name = f"{os.path.splitext(os.path.basename(pdf_key))[0]}_page_{page_num + 1}_image_{i + 1}.{image['filetype'].lower()}"
                            image_bytes = image['content']
                            destination_key = f"{DESTINATION_S3_PREFIX}{image_name}"

                            # Upload image to the destination S3 bucket
                            s3.put_object(Bucket=DESTINATION_S3_BUCKET, Key=destination_key, Body=image_bytes)
                            s3_uri = f"s3://{DESTINATION_S3_BUCKET}/{destination_key}"

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
                print(f"Error processing {pdf_key}: {e}")

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error listing or processing S3 objects: {e}")
        }

    return {
        'statusCode': 200,
        'body': json.dumps(output_data, indent=2)
    }