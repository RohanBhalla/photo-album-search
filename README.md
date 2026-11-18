# Photo Album Search

A photo album web app you can search with plain English ("show me dogs and cats").
Built on AWS: S3, Lambda, Rekognition, OpenSearch, Lex, API Gateway, CodePipeline and CloudFormation.

Cloud Computing and Big Data Systems, Fall 2026, Assignment 3.

## How it works

1. **Upload:** the frontend sends a photo to `PUT /photos` (API Gateway → S3 bucket B2), with optional custom labels in the `x-amz-meta-customLabels` header.
2. **Index:** the S3 upload triggers Lambda `index-photos` (LF1). It asks Rekognition what's in the photo, adds any custom labels, and saves the result in the OpenSearch `photos` index.
3. **Search:** the frontend calls `GET /search?q=...` → Lambda `search-photos` (LF2). LF2 sends the text to the Lex bot, which pulls out keywords, then searches OpenSearch and returns matching photos.

## Repo layout

| Folder | What's in it |
|---|---|
| `backend/index-photos/` | LF1: indexes uploaded photos |
| `backend/search-photos/` | LF2: handles search queries |
| `frontend/` | Static website (hosted on S3 bucket B1) |
| `lex/` | Lex bot definition (SearchIntent + utterances) |
| `infra/` | CloudFormation template (T1) and CodeBuild buildspecs |
| `docs/` | Notes and screenshots for submission |

## Requirements checklist

### 1. OpenSearch (ElasticSearch)
- [x] Create a domain called `photos`

### 2. Upload & index photos
- [x] S3 bucket B2 for photos
- [x] Lambda LF1 `index-photos`
- [x] S3 PUT event on B2 triggers LF1 (test: upload a file, check LF1 logs)
- [x] LF1 calls Rekognition `detectLabels`
- [x] LF1 reads `x-amz-meta-customLabels` with `headObject` and builds the labels array (A1)
- [x] LF1 stores `{objectKey, bucket, createdTimestamp, labels}` in the `photos` index

### 3. Search
- [x] Lambda LF2 `search-photos`
- [x] Lex bot with one intent `SearchIntent`
- [x] Utterances for keywords ("trees") and sentences ("show me trees and birds"), 1–2 keywords per query
- [x] LF2 sends query `q` to Lex, searches OpenSearch with the keywords, returns results per the API spec
- [x] Empty array when Lex finds no keywords

### 4. API layer (API Gateway)
- [x] API built from the [Swagger spec](https://github.com/001000001/ai-photo-search-columbia-f2018/blob/master/swagger.yaml)
- [x] `PUT /photos/{object}` as an S3 proxy, passing `x-amz-meta-customLabels`
- [x] `GET /search?q=` connected to LF2
- [x] API key on both methods
- [x] Deploy the API
- [x] Generate the JavaScript SDK (SDK1)

### 5. Frontend
- [x] Search box → `GET /search`
- [x] Show result photos
- [x] Upload form → `PUT /photos`, with custom labels sent as a comma-separated `x-amz-meta-customLabels` header
- [x] S3 bucket B1 with static website hosting
- [x] Upload frontend files to B1
- [x] Use SDK1 in the frontend

### 6. CodePipeline
- [x] P1: builds and deploys both Lambdas on push to GitHub
- [x] P2: deploys the frontend to B1 on push to GitHub

### 7. CloudFormation (T1)
- [x] Template that creates both Lambdas, API Gateway, and both S3 buckets (OpenSearch and CodePipeline optional)
- [x] Lambda code comes from the template or GitHub
- [x] Frontend bucket is public and its URL is an output

### Acceptance criteria
- [x] T1 creates the resources
- [x] A push to GitHub triggers build and deploy (frontend and backend)
- [x] Custom labels work end to end (mandatory)
- [x] Every Rekognition label and every custom label finds the photo, alone ("show me dogs") or in pairs ("show me cats and dogs")
- [x] Everything else works as described

## AWS setup

- Account: personal (`cc-hw1` profile), region `us-east-1`
- Copy `.env.example` to `.env` and fill it in. `.env` is git-ignored.

## Live URLs

- Website: http://photo-album-search-frontend-088850687383.s3-website-us-east-1.amazonaws.com
- API: https://4hknp7oxn6.execute-api.us-east-1.amazonaws.com/v1

## CloudFormation template (T1)

`infra/template.yaml` creates both S3 buckets (B1 public website, B2 photos with the upload trigger),
both Lambdas with inline code and their IAM roles, and the API Gateway API with an API key.
OpenSearch and the Lex bot are passed in as parameters (defaults point at the existing ones).

```bash
aws cloudformation deploy --stack-name photo-album-search-t1 \
  --template-file infra/template.yaml --capabilities CAPABILITY_IAM \
  --profile cc-hw1 --region us-east-1
aws cloudformation describe-stacks --stack-name photo-album-search-t1 \
  --query 'Stacks[0].Outputs' --profile cc-hw1 --region us-east-1
```

- Outputs: `WebsiteURL` (public frontend URL), `ApiURL`, `ApiKeyId`, bucket and function names.
- To change Lambda code: edit the inline `ZipFile` code in the template and run `deploy` again.
- All names are prefixed with the stack name, so it runs alongside the main deployment.
  Each search Lambda only returns photos from its own bucket, so they can share the `photos` index.

## Checking everything

```bash
.venv/bin/python scripts/check_requirements.py   # every assignment requirement against live AWS (30 checks)
.venv/bin/python scripts/test_search.py          # every label of every photo, alone and in pairs
```
