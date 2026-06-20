import json
import os
import logging
import urllib.request
import urllib.parse
import urllib.error

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

VALID_KEY_STAGES = {"ks1", "ks2", "ks3", "ks4"}
PAGE_LIMIT = 10
CONNECTION_TIMEOUT = 30


def validate_environment_variables():
    """
    Validate that all required environment variables are present.
    Returns a dict of validated values.
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
        'oak_api_key': os.environ.get('OAK_API_KEY'),
        'oak_api_url': os.environ.get('OAK_API_URL'),
    }


def validate_event(event):
    """
    Validate the event payload.
    Returns validated key_stage, subject, and units.
    Raises ValueError with descriptive message if validation fails.
    """
    key_stage = event.get('key_stage')
    subject = event.get('subject')
    units = event.get('units')

    errors = []

    if not key_stage or key_stage not in VALID_KEY_STAGES:
        errors.append(
            f"key_stage must be one of: {', '.join(sorted(VALID_KEY_STAGES))}"
        )

    if not subject or (isinstance(subject, str) and subject.strip() == ''):
        errors.append("subject is required and must be a non-empty string")

    if errors:
        raise ValueError("; ".join(errors))

    return key_stage, subject, units


def build_api_url(base_url, key_stage, subject, units, offset=0):
    """
    Construct the Oak API URL with query parameters.
    """
    url = f"{base_url}/key-stages/{key_stage}/subject/{subject}/lessons"

    params = []
    params.append(('limit', str(PAGE_LIMIT)))
    params.append(('offset', str(offset)))

    if units:
        for unit in units:
            params.append(('units', unit))

    query_string = urllib.parse.urlencode(params)
    return f"{url}?{query_string}"


def fetch_page(url, api_key):
    """
    Fetch a single page from the Oak API.
    Returns the parsed JSON response.
    Raises appropriate errors for HTTP failures and timeouts.
    """
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {api_key}')

    try:
        response = urllib.request.urlopen(req, timeout=CONNECTION_TIMEOUT)
        body = response.read().decode('utf-8')
        return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = ''
        try:
            error_body = e.read().decode('utf-8')
        except Exception:
            pass
        raise HTTPUpstreamError(e.code, error_body)
    except urllib.error.URLError as e:
        if 'timed out' in str(e.reason):
            raise ConnectionTimeoutError(url)
        raise ConnectionTimeoutError(url)


class HTTPUpstreamError(Exception):
    """Raised when the Oak API returns a non-success HTTP status."""

    def __init__(self, status_code, response_body):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"Upstream API returned status {status_code}")


class ConnectionTimeoutError(Exception):
    """Raised when connection to the Oak API times out."""

    def __init__(self, url):
        self.url = url
        super().__init__(f"Connection timeout reaching {url}")


def fetch_all_lessons(base_url, key_stage, subject, units, api_key):
    """
    Fetch all lesson slugs using pagination.
    Returns a list of lesson slug strings.
    """
    all_slugs = []
    offset = 0

    while True:
        url = build_api_url(base_url, key_stage, subject, units, offset)
        logger.info(f"Fetching lessons page at offset {offset}")

        data = fetch_page(url, api_key)

        # Extract lesson slugs from the response
        if isinstance(data, list):
            lessons = data
        else:
            lessons = data.get('results', data.get('lessons', []))

        for lesson in lessons:
            if isinstance(lesson, str):
                all_slugs.append(lesson)
            elif isinstance(lesson, dict):
                slug = lesson.get('slug', lesson.get('lessonSlug', ''))
                if slug:
                    all_slugs.append(slug)

        # Check if we've received fewer results than the limit (last page)
        if len(lessons) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

    return all_slugs


def lambda_handler(event, context):
    """
    Fetches lesson slugs from the Oak National Academy Open API for a given
    key stage, subject, and optional unit filters.

    Parameters:
    - event: The event data passed to the Lambda function. It should contain:
      - 'key_stage': One of ks1, ks2, ks3, ks4
      - 'subject': Non-empty subject identifier
      - 'units': (optional) Array of unit strings to filter by
    - context: The runtime information provided by AWS Lambda.

    Environment Variables:
    - 'OAK_API_KEY': API key for authenticating with the Oak API.
    - 'OAK_API_URL': Base URL of the Oak API.

    Returns:
    - A dictionary with statusCode and body containing lesson slugs in JSON format.
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

        # Validate event payload
        try:
            key_stage, subject, units = validate_event(event)
            logger.info(f"Processing request for key_stage={key_stage}, subject={subject}")
        except ValueError as e:
            logger.warning(f"Input validation failed: {e}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': str(e)})
            }

        # Fetch all lessons with pagination
        lesson_slugs = fetch_all_lessons(
            env_vars['oak_api_url'],
            key_stage,
            subject,
            units,
            env_vars['oak_api_key']
        )

        logger.info(f"Successfully fetched {len(lesson_slugs)} lesson slugs")

        return {
            'statusCode': 200,
            'body': json.dumps({'lesson_slugs': lesson_slugs})
        }

    except HTTPUpstreamError as e:
        logger.error(f"Oak API error: status={e.status_code}")
        return {
            'statusCode': 502,
            'body': json.dumps({
                'error': 'Upstream API error',
                'upstream_status': e.status_code,
                'upstream_body': e.response_body
            })
        }

    except ConnectionTimeoutError as e:
        logger.error(f"Connection timeout: {e.url}")
        return {
            'statusCode': 504,
            'body': json.dumps({
                'error': 'Connection timeout',
                'target_url': e.url
            })
        }

    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
