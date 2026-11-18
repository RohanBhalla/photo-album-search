"""Acceptance criterion 4 check: every label of every indexed photo must find that photo,
searched alone ("show me X") and in a pair ("show me X and Y").
Usage: .venv/bin/python scripts/test_search.py
"""
import itertools
import json
from urllib.parse import unquote, urlparse

import boto3

session = boto3.Session(profile_name="cc-hw1", region_name="us-east-1")
lam = session.client("lambda")
host = session.client("opensearch").describe_domain(DomainName="photos")["DomainStatus"]["Endpoint"]
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection  # noqa: E402

os_client = OpenSearch(hosts=[{"host": host, "port": 443}], use_ssl=True, verify_certs=True,
                       http_auth=AWSV4SignerAuth(session.get_credentials(), "us-east-1", "es"),
                       connection_class=RequestsHttpConnection, timeout=30)
docs = [h["_source"] for h in os_client.search(index="photos", body={"size": 1000})["hits"]["hits"]]


def found_keys(q):
    out = json.loads(lam.invoke(FunctionName="search-photos", Payload=json.dumps({"q": q}))["Payload"].read())
    return {unquote(urlparse(r["url"]).path.lstrip("/")) for r in out["results"]}


failures, total = [], 0
for doc in docs:
    others = [l for d in docs if d is not doc for l in d["labels"]] or ["tree"]
    for label, other in zip(doc["labels"], itertools.cycle(others)):
        for q in (f"show me {label}", f"show me {label} and {other}"):
            total += 1
            if doc["objectKey"] not in found_keys(q):
                failures.append((doc["objectKey"], q))

print(f"{total - len(failures)}/{total} searches found the right photo")
for key, q in failures:
    print(f"  MISS {key!r} for {q!r}")
