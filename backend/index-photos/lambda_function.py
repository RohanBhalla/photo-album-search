"""LF1 index-photos: runs on every S3 PUT to the photos bucket (B2).

For each uploaded photo it:
  1. asks Rekognition (DetectLabels) what is in the image
  2. reads custom labels from the object's x-amz-meta-customLabels metadata (headObject)
  3. stores {objectKey, bucket, createdTimestamp, labels} in the OpenSearch "photos" index
"""
import json
import logging
import os
from datetime import datetime
from urllib.parse import unquote_plus

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENSEARCH_HOST = os.environ["OPENSEARCH_HOST"]
INDEX = os.environ.get("OPENSEARCH_INDEX", "photos")
MAX_LABELS = int(os.environ.get("MAX_LABELS", "20"))
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "70"))

s3 = boto3.client("s3")
rekognition = boto3.client("rekognition")
search = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=AWSV4SignerAuth(boto3.Session().get_credentials(), REGION, "es"),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=20,
)


def parse_custom_labels(metadata):
    """Turn 'Sam, Sally' from x-amz-meta-customLabels into ['Sam', 'Sally'].

    S3 lowercases user metadata keys, so the header arrives as 'customlabels'.
    """
    raw = next((v for k, v in metadata.items() if k.lower() == "customlabels"), "")
    return [label.strip() for label in raw.split(",") if label.strip()]


def detect_labels(bucket, key):
    response = rekognition.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        MaxLabels=MAX_LABELS,
        MinConfidence=MIN_CONFIDENCE,
    )
    return [label["Name"] for label in response["Labels"]]


def unique(labels):
    """Drop repeats, ignoring case, but keep the first spelling and the order."""
    seen, result = set(), []
    for label in labels:
        if label.lower() not in seen:
            seen.add(label.lower())
            result.append(label)
    return result


def index_photo(bucket, key, event_time):
    head = s3.head_object(Bucket=bucket, Key=key)
    custom = parse_custom_labels(head.get("Metadata", {}))  # array A1
    detected = detect_labels(bucket, key)

    created = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    doc = {
        "objectKey": key,
        "bucket": bucket,
        "createdTimestamp": created.strftime("%Y-%m-%dT%H:%M:%S"),
        "labels": unique(custom + detected),
    }
    # Using bucket/key as the id means re-uploading a photo updates it instead of duplicating it.
    search.index(index=INDEX, id=f"{bucket}/{key}", body=doc)
    logger.info("Indexed %s", json.dumps(doc))
    return doc


def lambda_handler(event, context):
    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])  # keys arrive URL-encoded
        try:
            results.append(index_photo(bucket, key, record["eventTime"]))
        except rekognition.exceptions.InvalidImageFormatException:
            logger.warning("Skipping %s: not a JPEG or PNG image", key)
        except Exception:
            logger.exception("Failed to index %s", key)
            raise
    return {"indexed": len(results), "documents": results}
