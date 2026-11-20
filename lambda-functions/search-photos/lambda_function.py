"""LF2 search-photos: handles GET /search?q=<query text>.

  1. sends q to the Lex bot, which pulls out up to two keywords (K1, K2)
  2. if Lex found keywords, searches the OpenSearch "photos" index for any of them
  3. returns {"results": [{"url": ..., "labels": [...]}, ...]} as per the Swagger spec
     (an empty results array when Lex finds no keywords)
"""
import json
import logging
import os
import uuid

import boto3
from botocore.config import Config
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENSEARCH_HOST = os.environ["OPENSEARCH_HOST"]
INDEX = os.environ.get("OPENSEARCH_INDEX", "photos")
LEX_BOT_ID = os.environ["LEX_BOT_ID"]
LEX_BOT_ALIAS_ID = os.environ["LEX_BOT_ALIAS_ID"]
LEX_LOCALE = os.environ.get("LEX_LOCALE", "en_US")
URL_EXPIRY = int(os.environ.get("URL_EXPIRY_SECONDS", "3600"))
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "100"))
# Only return photos from this bucket. Other deployments (e.g. the CloudFormation T1 stack)
# share the same index, and this function can't make working links for their buckets.
PHOTOS_BUCKET = os.environ.get("PHOTOS_BUCKET", "")

lex = boto3.client("lexv2-runtime")
# SigV4 presigned URLs (the older SigV2 style is being retired by AWS)
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
search = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=AWSV4SignerAuth(boto3.Session().get_credentials(), REGION, "es"),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=20,
)

# Words that appear in search sentences but are never photo labels.
FILLER_WORDS = {
    "show", "me", "find", "search", "for", "get", "see", "want", "i", "to", "can", "you", "please",
    "photo", "photos", "picture", "pictures", "image", "images", "pic", "pics", "any",
    "of", "with", "in", "them", "it", "a", "an", "the", "and", "or", "some", "all",
}

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key,x-amz-meta-customLabels",
    "Access-Control-Allow-Methods": "GET,PUT,OPTIONS",
}


def get_keywords(query):
    """Ask Lex to disambiguate the query. Returns the keyword slot values (may be empty)."""
    response = lex.recognize_text(
        botId=LEX_BOT_ID,
        botAliasId=LEX_BOT_ALIAS_ID,
        localeId=LEX_LOCALE,
        sessionId=str(uuid.uuid4()),  # fresh session: every search stands alone
        text=query,
    )
    intent = response.get("sessionState", {}).get("intent", {})
    if intent.get("name") != "SearchIntent":
        return []
    keywords = []
    for slot in (intent.get("slots") or {}).values():
        value = ((slot or {}).get("value") or {}).get("interpretedValue")
        if value and value.lower() not in (k.lower() for k in keywords):
            keywords.append(value)
    if not keywords:
        # Safety net: Lex says this IS a search but didn't fill a slot (rare, e.g. "find Shiba Inu").
        # Search the query minus filler words instead of returning nothing.
        leftover = " ".join(w for w in query.split() if w.lower().strip("?.!,") not in FILLER_WORDS)
        keywords = [leftover] if leftover else []
        logger.info("Lex filled no slots for %r; using fallback keywords %s", query, keywords)
    return keywords


def search_photos(keywords):
    """Return photos whose labels match ANY keyword (case and plurals ignored by the index analyzer)."""
    body = {
        "size": MAX_RESULTS,
        "query": {
            "bool": {
                "should": [{"match": {"labels": k}} for k in keywords],
                "minimum_should_match": 1,
                "filter": [{"term": {"bucket": PHOTOS_BUCKET}}] if PHOTOS_BUCKET else [],
            }
        },
    }
    hits = search.search(index=INDEX, body=body)["hits"]["hits"]
    return [
        {
            "url": s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": hit["_source"]["bucket"], "Key": hit["_source"]["objectKey"]},
                ExpiresIn=URL_EXPIRY,
            ),
            "labels": hit["_source"]["labels"],
        }
        for hit in hits
    ]


def get_query(event):
    """Works with API Gateway (proxy or mapped) events and plain test events like {"q": "dogs"}."""
    params = event.get("queryStringParameters") or event.get("params", {}).get("querystring") or {}
    return (params.get("q") or event.get("q") or "").strip()


def respond(event, status, body):
    # API Gateway proxy integration wants statusCode/headers/body; direct calls get the plain body.
    if "requestContext" in event or "httpMethod" in event:
        return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}
    return body


def lambda_handler(event, context):
    query = get_query(event)
    try:
        keywords = get_keywords(query) if query else []
        results = search_photos(keywords) if keywords else []
        logger.info("v1.1 search q=%r keywords=%s results=%d", query, keywords, len(results))
        return respond(event, 200, {"results": results})
    except Exception as exc:
        logger.exception("Search failed for q=%r", query)
        return respond(event, 500, {"code": 500, "message": str(exc)})
