"""Send a signed request to the OpenSearch `photos` domain.

Usage:
  .venv/bin/python scripts/os.py GET /_cluster/health
  .venv/bin/python scripts/os.py PUT /photos '{"mappings": {...}}'
"""
import json
import os
import sys

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

REGION = os.environ.get("AWS_REGION", "us-east-1")
session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "cc-hw1"), region_name=REGION)
host = session.client("opensearch").describe_domain(DomainName="photos")["DomainStatus"]["Endpoint"]

client = OpenSearch(
    hosts=[{"host": host, "port": 443}],
    http_auth=AWSV4SignerAuth(session.get_credentials(), REGION, "es"),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)

method, path = sys.argv[1], sys.argv[2]
body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
print(json.dumps(client.transport.perform_request(method, path, body=body), indent=2))
