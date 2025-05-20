//fetch exitQuizzes from Oak Academy Open API and save all pdf-files in an S3 bucket

import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import https from 'https';
//throttle concurrency as otherwise it will run too many asset upload in parallel
// and hit limits
import pLimit from 'p-limit'; 
import { NodeHttpHandler } from "@smithy/node-http-handler";

const s3Client = new S3Client({
    region: "eu-west-2",
    requestHandler: new NodeHttpHandler({
      maxSockets: 100, // Or a higher value that suits your needs
    }),
  });

const API_KEY = process.env.OAK_API_KEY;
const BUCKET_NAME = process.env.S3_BUCKET_NAME;
const OAK_API_URL = process.env.OAK_API_URL; 

const fetchFromOakApi = async (url) => {
    return new Promise((resolve, reject) => {
        const options = {
            headers: {
                'Authorization': `Bearer ${API_KEY}`,
                'Accept': 'application/json'
            }
        };

        https.get(url, options, (response) => {
            if (response.statusCode !== 200) {
                reject(new Error(`HTTP Error: ${response.statusCode}`));
                return;
            }

            let data = '';
            response.on('data', (chunk) => data += chunk);
            response.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                } catch (error) {
                    reject(new Error('Failed to parse JSON response'));
                }
            });
            response.on('error', reject);
        }).on('error', reject);
    });
};

const fetchPdfContent = async (url) => {
    return new Promise((resolve, reject) => {
        const options = {
            headers: {
                'Authorization': `Bearer ${API_KEY}`,
                'Accept': 'application/pdf'
            }
        };

        https.get(url, options, (response) => {
            if (response.statusCode !== 200) {
                reject(new Error(`HTTP Error: ${response.statusCode}`));
                return;
            }

            const chunks = [];
            response.on('data', (chunk) => chunks.push(chunk));
            response.on('end', () => resolve(Buffer.concat(chunks)));
            response.on('error', reject);
        }).on('error', reject);
    });
};

const uploadToS3 = async (data, key) => {
    const command = new PutObjectCommand({
        Bucket: BUCKET_NAME,
        Key: key,
        Body: data,
        ContentType: 'application/pdf'
    });

    return s3Client.send(command);
};

const processAsset = async (asset, lessonSlug) => {
    try {
        console.log(`Processing asset: ${asset.type} for lesson: ${lessonSlug}`);
        
        const pdfData = await fetchPdfContent(asset.url);
        const filename = `${lessonSlug}/${asset.type}.pdf`;
        
        await uploadToS3(pdfData, filename);
        
        console.log(`Successfully uploaded ${filename} to S3`);
        return {
            success: true,
            filename,
            type: asset.type
        };
    } catch (error) {
        console.error(`Error processing asset: ${asset.url}`, error);
        return {
            success: false,
            error: error.message,
            asset
        };
    }
};


const processLesson = async (lesson) => {
    try {
        console.log(`Processing lesson: ${lesson.lessonSlug}`);

        const limit = pLimit(5); // Max 5 concurrent asset uploads

        const results = await Promise.all(
            lesson.assets.map(asset =>
                limit(() => processAsset(asset, lesson.lessonSlug))
            )
        );

        return {
            lessonSlug: lesson.lessonSlug,
            lessonTitle: lesson.lessonTitle,
            results
        };
    } catch (error) {
        console.error(`Error processing lesson: ${lesson.lessonSlug}`, error);
        return {
            lessonSlug: lesson.lessonSlug,
            error: error.message
        };
    }
};

export const handler = async (event) => {
    try {
        // Fetch lessons data from Oak API
        const lessonsData = await fetchFromOakApi(OAK_API_URL);
        
        if (!Array.isArray(lessonsData)) {
            throw new Error('Invalid response from Oak API');
        }

        console.log(`Processing ${lessonsData.length} lessons`);

        // Process each lesson
        const results = await Promise.all(
            lessonsData.map(lesson => processLesson(lesson))
        );

        return {
            statusCode: 200,
            body: JSON.stringify({
                message: 'Processing complete',
                results
            })
        };
    } catch (error) {
        console.error('Error in lambda handler:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({
                message: 'Error processing lessons',
                error: error.message
            })
        };
    }
};
