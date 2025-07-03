# Oak Bedrock Content Gen

A serverless project utilizing AWS Lambda and Amazon Bedrock to process Oak Academy exit quizzes, extract information, generate new questions, and create associated images.

This project is a personal exploration into automating the processing of educational content, specifically exit quizzes from the Oak Academy. It leverages AWS Lambda for serverless execution and Amazon Bedrock for advanced AI capabilities, including content summarization, question generation, and image creation.

**Current Status:** This project is actively under development and currently serves as a functional proof-of-concept. It demonstrates the core logic and interactions with AWS services and Amazon Bedrock models. Future iterations will focus on robust deployment, improved configurability, and expanded features.

The Oak Academy material contains exit quizzes for maths lessons based on UK curriculum. These exit quizzes containt questions and answers
and most of the exercises contain also an image that pupils can use to work through the question. The quizzes will be
processed in two steps - Nova Lite model will first extract the questions, describe images and based on those details
create a new similar question - answer pair and image description. Nova Canvas will then be used to create an image based
on the description using the original image as a 'conditioning image'. 

Further details about the experimental project is available in this [blog article](https://blog.marikabergman.com/maths-revision-material-via-amazon-nova-an-experiment).

![quiz_creation](./images/quiz_creation.png)

## The structure of the project

This project is comprised of several AWS Lambda functions, each residing in its own dedicated sub-folder.

**Infrastructure as Code:**
This project includes Infrastructure as Code (IaC) using AWS CloudFormation. All AWS resources (Lambda functions, S3 buckets, IAM roles) are automatically provisioned and configured through the deployment scripts.

**Automated Deployment:**
The project includes automated deployment scripts that handle packaging Lambda functions, uploading to S3, and deploying the CloudFormation stack.


## Oak-pdf-processor

This Lambda function pulls the exit quizzes from the Oak Academys API and saves then in an S3 bucket. An API key is required.
Currently the API is in beta and only exit quizzes for year groups 1 and 2 were available, hence the API call pulls all 
available resources. When the rest of the resources are available at the API, further filtering is required to get only one
year group at the time.

## Describe Quiz

This Lambda function calls the Amazon Bedrock Nova Lite model. The model will read one of the pdf files and write one of the question, determine a correct answer to the question and describe the image that is associated to the question. In addition,
it will create a new similar question - answer pair and create a description for an image that could be used with that question.

## createNewImage

This lambda function calls the Amazon Bedrock Nova Canvas model. This model is able to create images based on image and text input. The function uses the original image as the conditioning image. The text prompt is created combining a general prompt that describes the style and purpose of the image and a content prompt that comes from the output of Nova Lite Model. 

## extractImages

This Lambda function extracts images from the pdf files and saves them in a separate S3 bucket for further processing.

## Deployment

### Prerequisites
- AWS CLI configured with appropriate permissions
- AWS SSO login (if using SSO)
- Node.js and npm (for Node.js functions)
- Python 3 and pip3 (for Python functions)
- Oak Academy API key

### Deployment Commands

1. **Set up your environment:**
   ```bash
   # Login to AWS SSO (if using SSO)
   aws sso login --profile your-profile-name
   
   # Set your AWS profile and API key
   export AWS_PROFILE=your-profile-name
   export OAK_API_KEY="your-oak-academy-api-key"
   ```

2. **Package Lambda functions:**
   ```bash
   ./scripts/package-functions.sh
   ```

3. **Deploy to AWS:**
   ```bash
   # Deploy to us-east-1 (default)
   ./scripts/deploy.sh -r us-east-1
   
   # Or deploy with specific package timestamp
   ./scripts/deploy.sh -r us-east-1 -t YYYYMMDD-HHMMSS
   
   # Or deploy to different region
   ./scripts/deploy.sh -r us-west-2
   ```

4. **Complete deployment command:**
   ```bash
   export AWS_PROFILE=your-profile-name
   export OAK_API_KEY="your-api-key"
   ./scripts/package-functions.sh && ./scripts/deploy.sh -r us-east-1
   ```

### Deployment Scripts
- `scripts/package-functions.sh` - Packages all Lambda functions with dependencies
- `scripts/deploy.sh` - Uploads packages and deploys CloudFormation stack
- See `scripts/README.md` for detailed documentation

### Infrastructure Components
The CloudFormation template creates:
- **S3 Buckets**: PDF storage, image storage, and code storage
- **Lambda Functions**: All four processing functions with proper IAM roles
- **IAM Roles**: Least-privilege access for each function
- **Environment Variables**: Proper configuration for all functions 


## Next Steps

- **Frontend Application:** Create a web application that displays quiz questions and allows users to interact with the generated content
- **API Gateway Integration:** Add AWS API Gateway to provide RESTful endpoints for the frontend application to connect to the Lambda functions
- **End-to-End Testing:** Test the complete workflow from PDF processing through question generation to image creation
