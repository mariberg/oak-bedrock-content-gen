import boto3
import json
import os
import logging
from datetime import datetime, timezone

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def validate_environment_variables():
    """
    Validate that all required environment variables are present.
    Raises ValueError with descriptive message if any are missing.
    """
    required_vars = ['QUIZ_STORAGE_BUCKET']
    missing_vars = []

    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    return {
        'quiz_storage_bucket': os.environ.get('QUIZ_STORAGE_BUCKET')
    }


def distribute_questions(units, total=20):
    """
    Distribute questions equally across units, remainder to first alphabetically.

    Args:
        units: List of unit strings.
        total: Total number of questions to distribute (default 20).

    Returns:
        Dictionary mapping unit name to number of questions.
    """
    sorted_units = sorted(units)
    base = total // len(sorted_units)
    remainder = total % len(sorted_units)
    distribution = {}
    for i, unit in enumerate(sorted_units):
        distribution[unit] = base + (1 if i < remainder else 0)
    return distribution


def construct_bedrock_prompt(quiz_data, subject, key_stage, distribution):
    """
    Construct the Bedrock prompt for quiz generation.

    Args:
        quiz_data: Dictionary of quiz data keyed by lesson slug.
        subject: Subject identifier.
        key_stage: Key stage identifier.
        distribution: Dictionary mapping unit to question count.

    Returns:
        Tuple of (system_prompt_list, message_list).
    """
    system_list = [
        {
            "text": (
                "You are an expert quiz generator for educational content. "
                "You generate text-based quiz questions in structured JSON format. "
                "You MUST respond with ONLY a valid JSON array of question objects. "
                "Do NOT include any markdown formatting, code blocks, or explanatory text. "
                "Each question object must have exactly these fields: "
                "\"question_text\" (string), \"question_type\" (\"multiple_choice\" or \"short_answer\"), "
                "\"answer_options\" (array of strings for multiple choice, empty array for short answer), "
                "\"correct_answer\" (string), and \"unit\" (string identifying the source unit). "
                "Do NOT include any image references or image generation instructions. "
                "All questions must be text-only."
            )
        }
    ]

    distribution_instructions = "\n".join(
        f"- {unit}: {count} questions" for unit, count in distribution.items()
    )

    quiz_data_summary = json.dumps(quiz_data, indent=2)

    user_prompt = (
        f"Based on the following existing quiz data for {subject} at {key_stage} level, "
        f"generate exactly 20 new quiz questions.\n\n"
        f"Question distribution per unit:\n{distribution_instructions}\n\n"
        f"Existing quiz data for reference:\n{quiz_data_summary}\n\n"
        f"Generate questions that are similar in style and difficulty to the existing quizzes. "
        f"Each question must be assigned to its specified unit. "
        f"Return ONLY a JSON array of question objects with no additional text."
    )

    message_list = [
        {
            "role": "user",
            "content": [
                {"text": user_prompt}
            ]
        }
    ]

    return system_list, message_list


def validate_question_structure(questions):
    """
    Validate that each question has the required fields.

    Args:
        questions: List of question dictionaries.

    Returns:
        True if all questions are valid, raises ValueError otherwise.
    """
    required_fields = ['question_text', 'question_type', 'answer_options', 'correct_answer', 'unit']
    valid_types = ['multiple_choice', 'short_answer']

    for i, question in enumerate(questions):
        if not isinstance(question, dict):
            raise ValueError(f"Question {i + 1} is not a valid object")

        for field in required_fields:
            if field not in question:
                raise ValueError(f"Question {i + 1} missing required field: {field}")

        if question['question_type'] not in valid_types:
            raise ValueError(
                f"Question {i + 1} has invalid question_type: {question['question_type']}"
            )

        if not isinstance(question['answer_options'], list):
            raise ValueError(f"Question {i + 1} answer_options must be an array")

        if not question['question_text']:
            raise ValueError(f"Question {i + 1} has empty question_text")

        if not question['correct_answer']:
            raise ValueError(f"Question {i + 1} has empty correct_answer")

        if not question['unit']:
            raise ValueError(f"Question {i + 1} has empty unit")

    return True


def lambda_handler(event, context):
    """
    Generates a 20-question quiz using Amazon Bedrock Nova Lite model based on
    fetched quiz data, then stores the result in S3.

    Parameters:
    - event: The event data passed to the Lambda function. It should contain:
      - 'quiz_data': Dictionary of quiz data keyed by lesson slug.
      - 'subject': Subject identifier string.
      - 'key_stage': Key stage identifier string.
      - 'units': Array of unit strings.
      - 'lesson_slugs': (optional) Array of source lesson slug strings for metadata.
    - context: The runtime information provided by AWS Lambda.

    Environment Variables:
    - 'QUIZ_STORAGE_BUCKET': S3 bucket name for storing generated quizzes.

    Returns:
    - A dictionary with statusCode and body containing S3 key, question count,
      and units covered.
    """
    try:
        # Validate environment variables at function startup
        try:
            env_vars = validate_environment_variables()
            logger.info("Environment variables validated successfully")
        except ValueError as e:
            logger.error(f"Environment validation failed: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f"Configuration error: {e}"})
            }

        # Validate input payload
        missing_fields = []
        quiz_data = event.get('quiz_data')
        subject = event.get('subject')
        key_stage = event.get('key_stage')
        units = event.get('units')
        lesson_slugs = event.get('lesson_slugs', [])

        if quiz_data is None or not isinstance(quiz_data, dict):
            missing_fields.append('quiz_data')
        if not subject:
            missing_fields.append('subject')
        if not key_stage:
            missing_fields.append('key_stage')
        if units is None or not isinstance(units, list) or len(units) == 0:
            missing_fields.append('units')

        if missing_fields:
            error_msg = f"Missing or invalid required fields: {', '.join(missing_fields)}"
            logger.error(f"Invalid input: {error_msg}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_msg})
            }

        # Calculate question distribution
        distribution = distribute_questions(units)
        logger.info(f"Question distribution: {distribution}")

        # Construct Bedrock prompt
        system_list, message_list = construct_bedrock_prompt(
            quiz_data, subject, key_stage, distribution
        )

        # Invoke Bedrock Nova Lite model
        logger.info("Invoking Bedrock Nova Lite model")
        client = boto3.client("bedrock-runtime", region_name="us-east-1")
        MODEL_ID = "us.amazon.nova-lite-v1:0"

        inf_params = {
            "maxTokens": 3000,
            "topP": 0.1,
            "topK": 20,
            "temperature": 0.3
        }

        native_request = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": system_list,
            "inferenceConfig": inf_params,
        }

        try:
            response = client.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(native_request)
            )
            model_response = json.loads(response["body"].read())
        except Exception as e:
            logger.error(f"Bedrock invocation error: {type(e).__name__}: {e}")
            return {
                'statusCode': 502,
                'body': json.dumps({
                    'error': f"Bedrock model error: {str(e)}"
                })
            }

        # Parse JSON response from model
        content_text = model_response["output"]["message"]["content"][0]["text"]
        logger.info("Bedrock response received, parsing JSON")

        try:
            questions = json.loads(content_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bedrock response as JSON: {e}")
            logger.error(f"Raw response: {content_text[:500]}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Failed to parse model response as valid JSON'
                })
            }

        # Validate question structure
        try:
            validate_question_structure(questions)
        except ValueError as e:
            logger.error(f"Question validation failed: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': f"Invalid question structure: {str(e)}"
                })
            }

        # Construct S3 key with timestamp
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        s3_key = f"quizzes/{subject}/{key_stage}/{timestamp}.json"

        # Build quiz output with metadata
        generated_at = now.isoformat()
        quiz_output = {
            "metadata": {
                "subject": subject,
                "key_stage": key_stage,
                "units": units,
                "generated_at": generated_at,
                "source_lesson_slugs": lesson_slugs
            },
            "questions": questions
        }

        # Store quiz in S3
        bucket_name = env_vars['quiz_storage_bucket']
        logger.info(f"Storing quiz to s3://{bucket_name}/{s3_key}")

        try:
            s3 = boto3.client('s3')
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=json.dumps(quiz_output, indent=2),
                ContentType='application/json'
            )
        except Exception as e:
            logger.error(f"S3 write error: {type(e).__name__}: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': f"Failed to store quiz in S3: {str(e)}"
                })
            }

        logger.info(
            f"Quiz generated successfully: {len(questions)} questions, "
            f"units: {units}, s3_key: {s3_key}"
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                's3_key': s3_key,
                'question_count': len(questions),
                'units_covered': units
            })
        }

    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'An internal error occurred'})
        }
