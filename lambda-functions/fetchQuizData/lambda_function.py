//

import json
import os
import logging
import urllib.request
import urllib.error

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Request timeout in seconds
REQUEST_TIMEOUT = 30


def validate_environment_variables():
    """
    Validate that all required environment variables are present.
    Raises ValueError with descriptive message if any are missing.
    """
    required_vars = ['OAK_API_KEY', 'OAK_API_URL']
    missing_vars = []

    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    return {
        'api_key': os.environ.get('OAK_API_KEY'),
        'api_url': os.environ.get('OAK_API_URL')
    }


def fetch_quiz_for_lesson(slug, api_url, api_key):
    """
    Fetch quiz data for a single lesson slug from the Oak API.

    Returns the quiz data dict on success, or None if the lesson should be skipped.
    Raises no exceptions — all errors are handled internally and logged.
    """
    url = f"{api_url}/lessons/{slug}/quiz"
    logger.info(f"Fetching quiz data for lesson: {slug}")
    logger.info(f"Request URL: {url}")
    logger.info(f"Request headers: Authorization=Bearer <redacted>, length={len(api_key)} chars")

    request = urllib.request.Request(url)
    request.add_header('Authorization', f'Bearer {api_key}')
    request.add_header('User-Agent', 'Mozilla/5.0 (compatible; OakQuizFetcher/1.0)')
    request.add_header('Accept', 'application/json')

    try:
        response = urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)
        response_data = response.read().decode('utf-8')
        data = json.loads(response_data)

        # Check for empty or null quiz data
        if data is None:
            logger.warning(f"Null response for lesson '{slug}', skipping")
            return None

        # Handle cases where response has no quiz content
        if isinstance(data, dict):
            # API returns starterQuiz/exitQuiz at top level, or quiz as a nested field
            has_content = (
                data.get('starterQuiz') or
                data.get('exitQuiz') or
                data.get('quiz')
            )
            if not has_content:
                logger.warning(f"Empty quiz data for lesson '{slug}', skipping")
                return None
        elif data == [] or data == {}:
            logger.warning(f"Empty quiz data for lesson '{slug}', skipping")
            return None

        return data

    except urllib.error.HTTPError as e:
        error_body = ''
        try:
            error_body = e.read().decode('utf-8')
        except Exception:
            pass
        if e.code == 404:
            logger.warning(f"Lesson '{slug}' not found (404), skipping")
        else:
            logger.warning(
                f"Non-success HTTP status {e.code} for lesson '{slug}', skipping. "
                f"Response body: {error_body[:500]}"
            )
        return None

    except urllib.error.URLError as e:
        if 'timed out' in str(e.reason).lower():
            logger.warning(f"Timeout fetching quiz for lesson '{slug}', skipping")
        else:
            logger.warning(
                f"Connection error for lesson '{slug}': {e.reason}, skipping"
            )
        return None

    except TimeoutError:
        logger.warning(f"Timeout fetching quiz for lesson '{slug}', skipping")
        return None

    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON response for lesson '{slug}', skipping")
        return None

    except Exception as e:
        logger.warning(f"Unexpected error fetching quiz for lesson '{slug}': {type(e).__name__}, skipping")
        return None


def lambda_handler(event, context):
    """
    Fetches quiz data from the Oak National Academy API for a list of lesson slugs.
    Handles per-lesson errors gracefully by logging and skipping failures.

    Parameters:
    - event: The event data passed to the Lambda function. It should contain:
      - 'lesson_slugs': A non-empty array of lesson slug strings.
    - context: The runtime information provided by AWS Lambda.

    Environment Variables:
    - 'OAK_API_KEY': API key for authenticating with the Oak API.
    - 'OAK_API_URL': Base URL for the Oak API.

    Returns:
    - A dictionary with statusCode and body containing quiz data and processing summary.
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
        lesson_slugs = event.get('lesson_slugs')

        if lesson_slugs is None or not isinstance(lesson_slugs, list) or len(lesson_slugs) == 0:
            logger.error("Invalid input: lesson_slugs must be a non-empty array")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid input: lesson_slugs must be a non-empty array'
                })
            }

        api_url = env_vars['api_url']
        api_key = env_vars['api_key']
        total = len(lesson_slugs)
        logger.info(f"OAK_API_URL = {api_url}")
        logger.info(f"OAK_API_KEY length = {len(api_key)} chars")
        logger.info(f"Processing {total} lesson slugs")

        # Process each lesson slug
        quiz_data = {}
        skipped = 0

        for slug in lesson_slugs:
            result = fetch_quiz_for_lesson(slug, api_url, api_key)
            if result is not None:
                quiz_data[slug] = result
            else:
                skipped += 1

        processed = len(quiz_data)

        summary = {
            'processed': processed,
            'skipped': skipped,
            'total': total
        }

        logger.info(
            f"Processing complete: {processed} processed, {skipped} skipped, {total} total"
        )

        # Return 200 with warning if no quiz data retrieved
        if processed == 0:
            logger.warning("No quiz data retrieved for any lesson")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'quiz_data': {},
                    'summary': summary,
                    'warning': 'No quiz data was retrieved for any of the provided lesson slugs'
                })
            }

        return {
            'statusCode': 200,
            'body': json.dumps({
                'quiz_data': quiz_data,
                'summary': summary
            })
        }

    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'An internal error occurred'})
        }
