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
