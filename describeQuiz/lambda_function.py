import boto3
import json
import uuid
import base64

s3 = boto3.client('s3')

def lambda_handler(event, context):
    """
    Processes a PDF document using Amazon Bedrock to extract a specified question,
    determine its type (multiple choice or open-ended), identify answer options if present,
    calculate the correct answer, describe any associated image, generate a new question
    of the same type, provide its correct answer, and describe a potential hint-providing
    image for the new question. The extracted information and generated content,
    including the lesson name, are returned as a JSON object. The S3 location,
    bucket owner, and the number of the question to process are taken from the event.

    Parameters:
    - event: The event data passed to the Lambda function. It should contain:
      - 's3_uri': The S3 URI of the PDF document (e.g., 's3://bucket-name/path/to/file.pdf').
      - 'bucket_owner': The AWS account ID of the bucket owner.
      - 'question_number': The index (starting from 1) of the question to process.
    - context: The runtime information provided by AWS Lambda (not directly used in the current implementation).

    Returns:
    - A dictionary with statusCode and body containing the analysis result in JSON format.
    """
    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name="us-east-1",
        )
        MODEL_ID = "us.amazon.nova-lite-v1:0"

        s3_uri = event.get('s3_uri')
        bucket_owner = event.get('bucket_owner')
        question_number = event.get('question_number', 1)  # Default to the first question if not provided

        if not s3_uri or not bucket_owner:
            raise ValueError("Both 's3_uri' and 'bucket_owner' must be provided in the event.")

        s3_location_parts = s3_uri.replace("s3://", "").split("/")
        bucket_name = s3_location_parts[0]
        file_key = "/".join(s3_location_parts[1:])

        choose_question_instruction = f"Choose the {question_number} of these questions." if question_number > 1 else "Choose the first of these questions."

        system_list = [
            {
                "text": "You are an expert document analyst. Your task is to identify a question and describe the associated image in the provided PDF document. Additionally, you should create a new similar question and describe an image that could be associated to that question."
            }
        ]


        message_list = [
            {
                "role": "user",
                "content": [
                    {
                        "document": {
                            "format": "pdf",
                            "name": file_key,
                            "source": {
                                "s3Location": {
                                    "uri": s3_uri,
                                    "bucketOwner": bucket_owner
                                }
                            }
                        }
                    },
                    {
                    "text": f"Identify the lesson name present in the document. Identify all the questions present in the document. {choose_question_instruction} Write down the chosen question and ensure it is trimmed of any extra whitespace. If the question includes any blank space, mark that clearly with '_____'. Determine if the chosen question is multiple choice (provides answer options) or open ended. If it's multiple choice, extract all the answer options. Calculate the mathematically correct answer to the chosen question. Describe the image associated with the chosen question in very clear terms, including any numbers that might be included within the image (if an image is associated with the question). Based on this chosen question, create a new, mathematically valid and correct maths question of the *same type* (multiple choice if the original was, open ended if the original was) that would be suitable for a similar level/age group. If the new question is multiple choice, generate three plausible incorrect answer options in addition to the correct answer. Ensure the new question is trimmed of any extra whitespace and provide its correct answer. For the new question, describe a potential image that could be associated with it, ensuring that the image provides hints to help the student work out the answer without directly giving the solution. The image description should offer visual cues or representations that guide the student's thinking process rather than explicitly showing the answer. Return all this information as a single JSON object with exactly this format: {{ \"lesson_name\": \"[name of the lesson]\", \"original_question\": \"[trimmed question text]\", \"original_answer_options\": \"[a list of answer options if present, otherwise 'N/A']\",\"original_correct_answer\": \"[answer to original question]\", \"original_imageDescription\": \"[description of image for original question]\", \"new_question\": \"[trimmed new question text]\", \"new_answer_options\": \"[a list of answer options if generated, otherwise 'N/A']\", \"new_correct_answer\": \"[correct answer to new question]\", \"new_imageDescription\": \"[description of potential image for new question]\" }}"
                    }
                ]
            }
        ]

        inf_params = {"maxTokens": 3000, "topP": 0.1, "topK": 20, "temperature": 0.3}

        native_request = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": system_list,
            "inferenceConfig": inf_params,
        }

        response = client.invoke_model(modelId=MODEL_ID, body=json.dumps(native_request))
        model_response = json.loads(response["body"].read())

        content_text = model_response["output"]["message"]["content"][0]["text"]
        print("Raw model response content_text:")
        print(content_text)
        llm_output = json.loads(content_text)

        return {
            'statusCode': 200,
            'body': json.dumps(llm_output)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }