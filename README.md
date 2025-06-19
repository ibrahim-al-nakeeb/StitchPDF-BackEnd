# StitchPDF-BackEnd

**StitchPDF-BackEnd** is the serverless backend component for the StitchPDF application, built to handle PDF merging at scale. Users upload up to 5 PDF files through a drag-and-drop [interface](https://github.com/ibrahim-al-nakeeb/StitchPDF-FrontEnd.git) and define their order on the frontend. Once ready, the frontend uploads a `.json` file containing a `groupId`, which serves as a reference to the uploaded files. This file triggers the backend to perform the merge and make the result available for download.

---

## Cloud Architecture

The diagram below outlines the backend design of StitchPDF. It highlights how each AWS service is used, API Gateway exposes endpoints for generating pre-signed S3 URLs, S3 stores the uploaded files, and a Lambda function handles the merge when a trigger file is uploaded.

![Cloud Architecture Diagram](Cloud%20Architecture%20Diagram.svg)

---

## Features

* **Serverless architecture with AWS Lambda**

  All backend operations — including group ID generation, upload/download URL issuance, merge orchestration, and status polling — are handled by decoupled Lambda functions.

* **Stage-based S3 workflow**

  * **In-Process Bucket**: Temporarily stores uploaded PDFs and the trigger `.json` file (1-day lifecycle).
  * **Valid Bucket**: Stores successfully merged output PDFs (7-day lifecycle).
  * **Invalid Bucket**: Stores original PDFs if the merge fails (7-day lifecycle).

* **S3-triggered merge execution**

  Uploading a `.json` file to the In-Process bucket triggers the merge Lambda via an S3 event notification.

* **Pre-signed URL generation via API Gateway**

  Two Lambda-backed endpoints return secure, time-limited S3 URLs:

  * `PUT` URLs for uploading files (valid for 30 seconds)
  * `GET` URLs for downloading merged output (valid for 30 seconds)

* **Session tracking with DynamoDB**

  A DynamoDB table stores session metadata including `groupId`, creation time, TTL, and merge status (`PENDING`, `SUCCESS`, or `FAILED`).

* **Static frontend delivery via Amazon CloudFront**

  The React-based UI is hosted in an S3 bucket and served globally using CloudFront for fast and reliable access.

* **Monitoring and security**

  * **CloudWatch** captures logs for each Lambda execution.
  * **IAM** roles restrict access across S3, DynamoDB, and API Gateway to the minimum required.

---

## Workflow Overview

1. **Group ID Generation**

   The client sends a request to API Gateway, which invokes a [Lambda function](#generate-group-id) to generate a UUID-based `groupId`. The ID is stored in DynamoDB along with creation time, status (`PENDING`), and TTL for automatic expiration.

2. **File Upload**

   For each file, the client requests a pre-signed S3 `PUT` URL (valid for 30 seconds) via API Gateway. A [Lambda function](#generate-upload-presigned-url) validates the file extension (`.pdf` or `.json`) and generates the URL. The client uploads up to 5 PDF files to the **In-Process** S3 bucket using these URLs.

3. **Trigger File Upload**

   After uploading all PDFs, the client uploads a `.json` file containing only the `groupId` to the same S3 bucket. This upload triggers the [merge Lambda](#merge-files) via an S3 event notification.

4. **Merge Processing**

   The [merge Lambda](#merge-files) retrieves all files associated with the `groupId` from the **In-Process** bucket, attempts to merge them, and updates the status in DynamoDB:

   * If the merge succeeds, the output is written to the **Valid** bucket and status is set to `SUCCESS`.
   * If it fails, the original files are moved to the **Invalid** bucket and status is set to `FAILED`.

5. **Download**

   The client polls API Gateway for a download URL by providing the `groupId`. A [Lambda function](#generate-download-presigned-url) checks the status in DynamoDB:

   * If `SUCCESS`, it returns a pre-signed S3 `GET` URL (valid for 30 seconds).
   * If `FAILED`, it returns an error.
   * If still `PENDING`, it returns a respond with a 202 status.

6. **Cleanup**

   S3 lifecycle policies automatically remove:

   * Files in the **In-Process** bucket after **1 day**
   * Files in the **Valid** and **Invalid** buckets after **7 days**

   DynamoDB entries (merge sessions) expire automatically after **60 minutes** using the `expiresAt` TTL attribute.

---

## DynamoDB Schema

The `groupId` is stored in a DynamoDB table used to track merge sessions and control TTL-based cleanup.

**Primary Key:**

* `groupId` (Partition Key): A unique identifier for each merge session (UUID v4)

**Attributes:**

| Attribute   | Type   | Description                                             |
| ----------- | ------ | ------------------------------------------------------- |
| `groupId`   | String | Unique ID for the file group (PK)                       |
| `createdAt` | String | UTC ISO timestamp when the group was created            |
| `expiresAt` | Number | UNIX timestamp used for TTL (auto-expire after 60 mins) |
| `status`    | String | Merge status (e.g. `PENDING`, `DONE`, `FAILED`)         |

**TTL Configuration:**

* The `expiresAt` attribute is used for DynamoDB's TTL mechanism
* Expired items are automatically removed after 60 minutes

---

## Merge Trigger: `trigger.json` Upload

The merge operation is initiated by uploading a `.json` file (commonly named `trigger.json`) to the **In-Process** S3 bucket. This file contains a single field: the `groupId`, which corresponds to the folder prefix where the user’s uploaded PDF files are stored.

### Expected Format

```json
{
  "groupId": "uuid-v4"
}
```

### Behavior

* When the `.json` file is uploaded, it triggers the [merge Lambda function](#merge-files) via an S3 event notification.

### Notes

* The trigger file must be placed in the same prefix as the uploaded PDF files.
* It must contain a valid `groupId` or the merge will fail.
* The `.json` file itself is ignored during the merge.

---

## Lambda Configuration

### `generate-group-id`

This Lambda function generates a unique `groupId` used to identify and organize uploaded PDF files. It writes an entry to a DynamoDB table and ensures uniqueness using a conditional write.

**Purpose:**

* Generate a new UUID `groupId`
* Store the group in DynamoDB with creation and expiration timestamps
* Ensure the ID is unique using `ConditionExpression`

**Environment Variables:**

| Name             | Description                                       | Required |
| ---------------- | ------------------------------------------------- | -------- |
| `TABLE_NAME`     | Name of the DynamoDB table storing group metadata | ✅        |
| `ALLOWED_ORIGIN` | Allowed CORS origin for API Gateway responses     | ✅        |

**Behavior Notes:**

* Makes up to 5 attempts to avoid `groupId` collisions (very unlikely with UUIDv4)
* Uses TTL (`expiresAt`) to auto-delete stale items after 60 minutes
* Returns `groupId` on success or a 500 error on repeated failure or unexpected errors

**Example Response:**

```json
{
  "groupId": "uuid-v4"
}
```

**Possible Status Codes:**

| Code | Meaning                                                                              |
| ---- | ------------------------------------------------------------------------------------ |
| 200  | Successfully generated and stored a new `groupId`                                    |
| 500  | Failed to store `groupId` after multiple attempts or other unexpected DynamoDB error |


---

### `generate-upload-presigned-url`

This Lambda function generates a pre-signed S3 `PUT` URL for securely uploading a `.pdf` or `.json` file to the appropriate location in the S3 bucket.

**Purpose:**

* Validates file type and presence of the `filename` query parameter
* Generates a secure, time-limited pre-signed URL for direct S3 upload
* Supports uploading `.pdf` (document) and `.json` (merge trigger) files

**Environment Variables:**

| Name             | Description                                         | Required |
| ---------------- | --------------------------------------------------- | -------- |
| `BUCKET_NAME`    | Target S3 bucket for file uploads                   | ✅        |
| `EXPIRATION`     | Expiration time (in seconds) for the pre-signed URL | ✅        |
| `ALLOWED_ORIGIN` | Allowed CORS origin for the response                | ✅        |

**Behavior Notes:**

* Only files with `.pdf` or `.json` extensions are accepted
* Returns HTTP 400 for missing or unsupported `filename`
* Uses `put_object` to grant direct upload access
* The returned URL is valid for the duration defined by `EXPIRATION`

**Example Response:**

```json
{
  "presigned_url": "https://in-process-files.s3.amazonaws.com/groupId/file.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&..."
}
```

**Possible Status Codes:**

| Code | Meaning                                                      |
| ---- | ------------------------------------------------------------ |
| 200  | Pre-signed upload URL successfully generated                 |
| 400  | Missing `filename` query parameter or unsupported file type  |
| 500  | Internal error during URL generation (e.g., S3 or env issue) |

---

### `generate-download-presigned-url`

This Lambda function generates a pre-signed S3 `GET` URL to download a merged PDF file associated with a specific `groupId`. It queries DynamoDB to check the merge status.

**Purpose:**

* Check the merge status of a file group in DynamoDB
* Return a pre-signed S3 `GET` URL for the merged PDF if available

**Environment Variables:**

| Name             | Description                                                     | Required |
| ---------------- | --------------------------------------------------------------- | -------- |
| `TABLE_NAME`     | DynamoDB table storing group metadata                           | ✅        |
| `BUCKET_NAME`    | S3 bucket where merged files are stored                         | ✅        |
| `EXPIRATION`     | Expiration time (in seconds) for the pre-signed download URL    | ✅        |
| `ALLOWED_ORIGIN` | Allowed CORS origin for the HTTP response                       | ✅        |

**Behavior Notes:**

* Checks DynamoDB for `groupId` status (`SUCCESS`, `FAILED`, or `PENDING`)
* If `SUCCESS`, generates a pre-signed `GET` URL valid for `EXPIRATION` seconds
* If `FAILED`, returns a 400 error with an appropriate message
* If still `PENDING`, returns a 202 response

**Example Response:**

```json
{
  "presigned_url": "https://stitchpdf-valid-files.s3.amazonaws.com/be2939b2.../merged_output.pdf?X-Amz-Algorithm=AWS4..."
}
```

**Possible Status Codes:**

| Code | Meaning                                 |
| ---- | --------------------------------------  |
| 200  | Download link successfully generated    |
| 202  | Merge still in progress                 |
| 400  | Missing or failed merge                 |
| 404  | No record found for the given `groupId` |
| 500  | Internal error (DynamoDB/S3 exception)  |

---

### `merge-files`

This Lambda function is triggered by an S3 `PutObject` event when a `.json` file is uploaded to the **In-Process** bucket. It reads the `groupId` from the JSON file, retrieves all associated PDFs, merges them, uploads the result to the **Valid** bucket (if successful), or moves files to the **Invalid** bucket (if failed). It updates the merge status in DynamoDB accordingly.

**Purpose:**

* Parse the uploaded trigger `.json` file to extract the `groupId`
* List and sort `.pdf` files associated with that group
* Merge the files using `PyPDF2`
* Upload the merged output or move the originals to the Invalid bucket on failure
* Update DynamoDB with `SUCCESS` or `FAILED` status

**Environment Variables:**

| Name                   | Description                                        | Required |
| ---------------------- | -------------------------------------------------- | -------- |
| `TABLE_NAME`           | DynamoDB table used to track group metadata        | ✅        |
| `VALID_FILES_BUCKET`   | S3 bucket to store successfully merged PDFs        | ✅        |
| `INVALID_FILES_BUCKET` | S3 bucket to store original files on merge failure | ✅        |

**Behavior Notes:**

* Uses `LastModified` to determine merge order
* Triggered only by `.json` files in the In-Process bucket
* Ignores the `.json` file itself during merging
* Dynamically handles merge failures and partial errors gracefully
* Configured with increased memory and timeout settings to support large file operations and longer processing times

**Possible Status Codes:**

| Code | Meaning                                                          |
| ---- | ---------------------------------------------------------------- |
| —    | Not an API-invoked Lambda (S3-triggered)                         |
| N/A  | Errors are logged and surfaced via CloudWatch or calling service |

---

## Required AWS Permissions per Lambda

### `generate-group-id`

#### S3

❌ No S3 access required

#### DynamoDB

| Action                        | Resource                                   | Purpose                        |
| ----------------------------- | ------------------------------------------ | ------------------------------ |
| `dynamodb:PutItem`            | `arn:aws:dynamodb:*:*:table/<FILE_GROUPS>` | Create a new group entry       |
| `dynamodb:ConditionCheckItem` | (implicit via `ConditionExpression`)       | Ensure uniqueness of `groupId` |

---

### `generate-upload-presigned-url`

#### S3

| Action         | Resource                             | Purpose                         |
| -------------- | ------------------------------------ | ------------------------------- |
| `s3:PutObject` | `arn:aws:s3:::<IN_PROCESS_BUCKET>/*` | Upload files via pre-signed URL |

#### DynamoDB

❌ No DynamoDB access required

---

### `generate-download-presigned-url`

#### S3

| Action          | Resource                              | Purpose                                  |
| --------------- | ------------------------------------- | ---------------------------------------- |
| `s3:GetObject`  | `arn:aws:s3:::<VALID_FILES_BUCKET>/*` | Generate pre-signed download URL         |
| `s3:ListBucket` | `arn:aws:s3:::<VALID_FILES_BUCKET>`   | Validate existence of merged output file |

#### DynamoDB

| Action             | Resource                                   | Purpose                            |
| ------------------ | ------------------------------------------ | ---------------------------------- |
| `dynamodb:GetItem` | `arn:aws:dynamodb:*:*:table/<FILE_GROUPS>` | Check merge status for the groupId |

---

### `merge-files`

#### S3

| Action          | Resource                                | Purpose                               |
| --------------- | --------------------------------------- | ------------------------------------- |
| `s3:ListBucket` | `arn:aws:s3:::<IN_PROCESS_BUCKET>`      | List `.pdf` files by prefix (groupId) |
| `s3:GetObject`  | `arn:aws:s3:::<IN_PROCESS_BUCKET>/*`    | Read `.pdf` and `.json` files         |
| `s3:PutObject`  | `arn:aws:s3:::<VALID_FILES_BUCKET>/*`   | Upload successfully merged PDF        |
| `s3:PutObject`  | `arn:aws:s3:::<INVALID_FILES_BUCKET>/*` | Store failed merge inputs             |

#### DynamoDB

| Action                | Resource                                   | Purpose                                  |
| --------------------- | ------------------------------------------ | ---------------------------------------- |
| `dynamodb:UpdateItem` | `arn:aws:dynamodb:*:*:table/<FILE_GROUPS>` | Update merge status (`SUCCESS`/`FAILED`) |

---

## Tech Stack

* **Runtime**: Python 3.13
* **Cloud Services**: AWS Lambda, S3, API Gateway, CloudFront, DynamoDB, IAM
* **Libraries**: `PyPDF2`, `boto3`, `uuid`, `json`, `datetime`, `botocore`, `time`, `os`

---

## Implementation Details

* All Lambdas use **API Gateway proxy integration**, allowing full request context. Developers can customize the integration for learning or extension to practice configuring custom request/response mappings.

* File merge order is based on the `LastModified` timestamp in S3, not the filename or upload request order.

---

### Final Note

This project was my introduction to serverless computing and the AWS ecosystem. It gave me hands-on experience with event-driven architecture, Lambda functions, and API Gateway integrations — all while building something practical and production-ready.
