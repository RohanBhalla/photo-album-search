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
- [ ] Create a domain called `photos`

### 2. Upload & index photos
- [ ] S3 bucket B2 for photos
- [ ] Lambda LF1 `index-photos`
- [ ] S3 PUT event on B2 triggers LF1 (test: upload a file, check LF1 logs)
- [ ] LF1 calls Rekognition `detectLabels`
- [ ] LF1 reads `x-amz-meta-customLabels` with `headObject` and builds the labels array (A1)
- [ ] LF1 stores `{objectKey, bucket, createdTimestamp, labels}` in the `photos` index

### 3. Search
- [ ] Lambda LF2 `search-photos`
- [ ] Lex bot with one intent `SearchIntent`
- [ ] Utterances for keywords ("trees") and sentences ("show me trees and birds"), 1–2 keywords per query
- [ ] LF2 sends query `q` to Lex, searches OpenSearch with the keywords, returns results per the API spec
- [ ] Empty array when Lex finds no keywords

### 4. API layer (API Gateway)
- [ ] API built from the [Swagger spec](https://github.com/001000001/ai-photo-search-columbia-f2018/blob/master/swagger.yaml)
- [ ] `PUT /photos` as an S3 proxy, passing `x-amz-meta-customLabels`
- [ ] `GET /search?q=` connected to LF2
- [ ] API key on both methods
- [ ] Deploy the API
- [ ] Generate the JavaScript SDK (SDK1)

### 5. Frontend
- [ ] Search box → `GET /search`
- [ ] Show result photos
- [ ] Upload form → `PUT /photos`, with custom labels sent as a comma-separated `x-amz-meta-customLabels` header
- [ ] S3 bucket B1 with static website hosting
- [ ] Upload frontend files to B1
- [ ] Use SDK1 in the frontend

### 6. CodePipeline
- [ ] P1: builds and deploys both Lambdas on push to GitHub
- [ ] P2: deploys the frontend to B1 on push to GitHub

### 7. CloudFormation (T1)
- [ ] Template that creates both Lambdas, API Gateway, and both S3 buckets (OpenSearch and CodePipeline optional)
- [ ] Lambda code comes from the template or GitHub
- [ ] Frontend bucket is public and its URL is an output

### Acceptance criteria
- [ ] T1 creates the resources
- [ ] A push to GitHub triggers build and deploy (frontend and backend)
- [ ] Custom labels work end to end (mandatory)
- [ ] Every Rekognition label and every custom label finds the photo, alone ("show me dogs") or in pairs ("show me cats and dogs")
- [ ] Everything else works as described

## AWS setup

- Account: personal (`cc-hw1` profile), region `us-east-1`
- Copy `.env.example` to `.env` and fill it in. `.env` is git-ignored.
