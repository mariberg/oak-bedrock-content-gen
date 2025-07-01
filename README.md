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

**Important Note on Infrastructure:**
Currently, this repository **does not include Infrastructure as Code (IaC)**. The AWS resources (Lambda functions, S3 buckets, IAM roles) need to be provisioned manually. The names of other AWS resources are presently hardcoded within the Lambda function code.

Below, you'll find descriptions of each Lambda function along with the necessary AWS IAM permissions required for them to interact with other AWS resources.

**Required Manual Setup:**
* You need to create **two S3 buckets** that are essential for this project to function.
* The names of these buckets (and potentially other resources) are hardcoded. Future improvements will address this through configuration or IaC.


## Oak-pdf-processor

This Lambda function pulls the exit quizzes from the Oak Academys API and saves then in an S3 bucket. An API key is required.
Currently the API is in beta and only exit quizzes for year groups 1 and 2 were available, hence the API call pulls all 
available resources. When the rest of the resources are available at the API, further filtering is required to get only one
year group at the time.

Permissions:
- Ensure your IAM role has necessary 'putObject' permissions to the S3 bucket


## Describe Quiz

This Lambda function calls the Amazon Bedrock Nova Lite model. The model will read one of the pdf files and write one of the question, determine a correct answer to the question and describe the image that is associated to the question. In addition,
it will create a new similar question - answer pair and create a description for an image that could be used with that question.

Permissions:
- Ensure your IAM role has necessary 'getObject' permissions to the S3 bucket
- Ensure your IAM role has the necessary permissions to access Amazon Bedrock and the specific models you are using

## createNewImage

This lambda function calls the Amazon Bedrock Nova Canvas model. This model is able to create images based on image and text input. The function uses the original image as the conditioning image. The text prompt is created combining a general prompt that describes the style and purpose of the image and a content prompt that comes from the output of Nova Lite Model. 

Permissions: Ensure your IAM role has the necessary permissions to access Amazon Bedrock and the specific models you are using

## WIP - extraImages

**WIP** This Lambda function extracts images from the pdf files and saves then in a separate S3 bucket. 


## Future Enhancements / Roadmap

* **Infrastructure as Code (IaC):** Implement IaC using AWS Cloudformation to automate the deployment and management of all AWS resources. This will significantly improve reproducibility and maintainability.
* **Parameterization/Configuration:** Externalize hardcoded resource names (e.g., S3 bucket names, API keys) into environment variables.
* **Error Handling and Logging:** Enhance error handling within Lambda functions and improve logging for better observability and debugging.
* **API Gateway:** Consider exposing some functionality via API Gateway for external interaction.
