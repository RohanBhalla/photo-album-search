"""Check every Assignment 3 requirement against the live AWS setup. Prints PASS/FAIL per item.

Usage: .venv/bin/python other-scripts/check_requirements.py
Safe to re-run: it uploads one test photo (key "requirements-check.jpg") and searches for it.
"""
import json
import pathlib
import time
import urllib.parse
import urllib.request
import uuid

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = dict(l.split("=", 1) for l in (ROOT / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))
A, R = "088850687383", "us-east-1"
B1, B2 = ENV["FRONTEND_BUCKET"], ENV["PHOTOS_BUCKET"]
API_URL, API_KEY = ENV["API_GATEWAY_URL"], ENV["API_KEY"]
API_ID = urllib.parse.urlparse(API_URL).hostname.split(".")[0]
BOT, ALIAS = ENV["LEX_BOT_ID"], ENV["LEX_BOT_ALIAS_ID"]
WEBSITE = f"http://{B1}.s3-website-{R}.amazonaws.com"
T1_STACK = "photo-album-search-t1"

s = boto3.Session(profile_name="cc-hw1", region_name=R)
c = {n: s.client(n) for n in ["opensearch", "s3", "lambda", "lexv2-models", "apigateway",
                                "codepipeline", "codebuild", "cloudformation", "logs"]}
osc = OpenSearch(hosts=[{"host": ENV["OPENSEARCH_ENDPOINT"], "port": 443}], use_ssl=True, verify_certs=True,
                 http_auth=AWSV4SignerAuth(s.get_credentials(), R, "es"),
                 connection_class=RequestsHttpConnection, timeout=30)
results = []


def check(section, name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # a crash counts as a failure, with the reason
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {section} {name}" + (f"  ({detail})" if detail else ""))


def http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def search(q, url=API_URL, key=API_KEY):
    code, body, _ = http("GET", f"{url}/search?q={urllib.parse.quote(q)}", {"x-api-key": key})
    return code, (json.loads(body)["results"] if code == 200 else [])


def keys(rs):
    return {urllib.parse.unquote(urllib.parse.urlparse(r["url"]).path.lstrip("/")) for r in rs}


def resources(rest_api_id):
    return {i["path"]: i for i in c["apigateway"].get_resources(restApiId=rest_api_id, embed=["methods"])["items"]}


# ---------------------------------------------------------------- 1. OpenSearch
print("\n1. OpenSearch")
check("1a", "domain 'photos' exists and is green", lambda: (
    (st := c["opensearch"].describe_domain(DomainName="photos")["DomainStatus"]) and not st["Processing"]
    and osc.cluster.health()["status"] == "green", st["EngineVersion"]))

# ---------------------------------------------------------------- 2. Upload & index
print("\n2. Upload & index photos")
check("2a", "photos bucket B2 exists, private", lambda: (
    all(c["s3"].get_public_access_block(Bucket=B2)["PublicAccessBlockConfiguration"].values()), B2))
check("2b", "Lambda LF1 'index-photos' exists", lambda: (
    c["lambda"].get_function(FunctionName="index-photos")["Configuration"]["State"] == "Active", None))
check("2c", "S3 PUT event on B2 triggers LF1", lambda: (
    any("s3:ObjectCreated:Put" in x["Events"] and x["LambdaFunctionArn"].endswith(":index-photos")
        for x in c["s3"].get_bucket_notification_configuration(Bucket=B2)["LambdaFunctionConfigurations"]), None))

# Fresh end-to-end upload through the API (PUT /photos) with custom labels.
TAG = "Chk" + uuid.uuid4().hex[:6]
KEY = "requirements-check.jpg"
photo = (ROOT / "docs" / "test-photos" / "cat.jpg").read_bytes()
up_code, _, _ = http("PUT", f"{API_URL}/photos/{KEY}", {"x-api-key": API_KEY, "Content-Type": "image/jpeg",
                                                         "x-amz-meta-customLabels": f"{TAG}, Grader"}, photo)
doc = {}
for _ in range(15):  # wait for LF1 to index it
    time.sleep(3)
    hit = osc.search(index="photos", body={"query": {"bool": {"filter": [
        {"term": {"bucket": B2}}, {"term": {"objectKey": KEY}}]}}})["hits"]["hits"]
    if hit and TAG in hit[0]["_source"]["labels"]:
        doc = hit[0]["_source"]
        break
check("2d-i", "LF1 adds Rekognition labels", lambda: (len(doc.get("labels", [])) > 2, f"{doc.get('labels')}"))
check("2d-ii", "LF1 reads x-amz-meta-customLabels (headObject) into labels", lambda: (
    doc.get("labels", [])[:2] == [TAG, "Grader"], None))
check("2d-iii", "index doc matches schema {objectKey, bucket, createdTimestamp, labels}", lambda: (
    set(doc) == {"objectKey", "bucket", "createdTimestamp", "labels"} and doc["bucket"] == B2, None))

# ---------------------------------------------------------------- 3. Search
print("\n3. Search")
check("3a", "Lambda LF2 'search-photos' exists", lambda: (
    c["lambda"].get_function(FunctionName="search-photos")["Configuration"]["State"] == "Active", None))
intents = c["lexv2-models"].list_intents(botId=BOT, botVersion="DRAFT", localeId="en_US")["intentSummaries"]
check("3b-i", "Lex bot has one intent 'SearchIntent'", lambda: (
    [i["intentName"] for i in intents if i["intentName"] != "FallbackIntent"] == ["SearchIntent"],
    "plus Lex's built-in FallbackIntent"))
iid = next(i["intentId"] for i in intents if i["intentName"] == "SearchIntent")
utts = [u["utterance"] for u in c["lexv2-models"].describe_intent(
    botId=BOT, botVersion="DRAFT", localeId="en_US", intentId=iid)["sampleUtterances"]]
check("3b-ii", "utterances cover keywords and sentences, 1-2 keywords", lambda: (
    "{keywordOne}" in utts and "show me {keywordOne}" in utts
    and any("{keywordTwo}" in u for u in utts), f"{len(utts)} utterances"))
check("3c", "keyword search: 'trees'-style single word", lambda: (KEY in keys(search(TAG)[1]), None))
check("3c", "sentence search: 'show me <label>'", lambda: (KEY in keys(search(f"show me {TAG}")[1]), None))
check("3c-iii", "no keywords -> empty results array", lambda: (search("hello")[1] == [], None))

# ---------------------------------------------------------------- 4. API
print("\n4. API Gateway")
res = resources(API_ID)
check("4b-i", "PUT /photos is an S3 proxy passing x-amz-meta-customLabels", lambda: (
    (i := res["/photos/{object}"]["resourceMethods"]["PUT"]["methodIntegration"])["type"] == "AWS"
    and ":s3:path/" in i["uri"]
    and "integration.request.header.x-amz-meta-customLabels" in i["requestParameters"], None))
check("4b-ii", "GET /search connected to LF2", lambda: (
    res["/search"]["resourceMethods"]["GET"]["methodIntegration"]["uri"].endswith(":search-photos/invocations"), None))
check("4c", "API key required on both methods", lambda: (
    res["/search"]["resourceMethods"]["GET"]["apiKeyRequired"]
    and res["/photos/{object}"]["resourceMethods"]["PUT"]["apiKeyRequired"]
    and search("dogs", key="wrong")[0] == 403, "403 without a valid key"))
check("4d", "API deployed (stage v1)", lambda: (
    c["apigateway"].get_stage(restApiId=API_ID, stageName="v1")["deploymentId"] != "", API_URL))
check("4e", "JavaScript SDK generated (SDK1)", lambda: (
    API_URL in (ROOT / "front-end" / "sdk" / "apigClient.js").read_text(), "front-end/sdk/"))

# ---------------------------------------------------------------- 5. Frontend
print("\n5. Frontend")
site = {p: http("GET", f"{WEBSITE}/{p}") for p in ["", "app.js", "config.js"]}
check("5a", "page has search, results and upload with custom labels", lambda: (
    all(x in site[""][1].decode() for x in ["search-form", "results", "upload-form", "tag-input"])
    and b"x-amz-meta-customLabels" in site["app.js"][1] and b'tags.join(", ")' in site["app.js"][1], None))
check("5b/c", "B1 has static website hosting and is public", lambda: (
    c["s3"].get_bucket_website(Bucket=B1)["IndexDocument"]["Suffix"] == "index.html"
    and site[""][0] == 200 and site[""][2].get("Content-Type") == "text/html", WEBSITE))
check("5d", "frontend files uploaded to B1", lambda: (site["app.js"][0] == 200 and site["config.js"][0] == 200, None))
check("5e", "frontend uses the SDK (apigClient)", lambda: (
    b"sdk/apigClient.js" in site[""][1] and b"client.searchGet" in site["app.js"][1]
    and b"client.photosObjectPut" in site["app.js"][1], None))

# ---------------------------------------------------------------- 6. CodePipeline
print("\n6. CodePipeline")
def pipeline_ok(name, project, path_glob):
    p = c["codepipeline"].get_pipeline(name=name)["pipeline"]
    paths = p["triggers"][0]["gitConfiguration"]["push"][0]["filePaths"]["includes"]
    last = c["codepipeline"].list_pipeline_executions(pipelineName=name, maxResults=1)["pipelineExecutionSummaries"][0]
    return (p["stages"][1]["actions"][0]["configuration"]["ProjectName"] == project and path_glob in paths
            and last["status"] == "Succeeded"), f"last run {last['status']}, trigger {last['trigger']['triggerType']}"
check("6a", "P1 builds + deploys Lambdas on push to lambda-functions/", lambda: pipeline_ok(
    "photo-album-backend-pipeline", "photo-album-backend", "lambda-functions/**"))
check("6b", "P2 deploys frontend to B1 on push to front-end/", lambda: pipeline_ok(
    "photo-album-frontend-pipeline", "photo-album-frontend", "front-end/**"))

# ---------------------------------------------------------------- 7. CloudFormation
print("\n7. CloudFormation (T1)")
stack = c["cloudformation"].describe_stacks(StackName=T1_STACK)["Stacks"][0]
types = {r["ResourceType"] for r in c["cloudformation"].list_stack_resources(StackName=T1_STACK)["StackResourceSummaries"]}
out = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
check("7a", "stack creates both Lambdas, API Gateway, both buckets, IAM roles", lambda: (
    stack["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE")
    and {"AWS::Lambda::Function", "AWS::ApiGateway::RestApi", "AWS::S3::Bucket", "AWS::IAM::Role"} <= types,
    stack["StackStatus"]))
check("7b", "Lambda code is in the template (inline)", lambda: (
    "ZipFile:" in (ROOT / "other-scripts" / "infra" / "template.yaml").read_text(), "other-scripts/infra/template.yaml"))
check("7c", "frontend bucket is a public webpage, URL is an output", lambda: (
    http("GET", out["WebsiteURL"])[0] == 200, out["WebsiteURL"]))

# ---------------------------------------------------------------- Acceptance criteria
print("\nAcceptance criteria")
check("AC3", "custom labels work end to end (upload -> search finds it)", lambda: (
    up_code == 200 and KEY in keys(search("show me Grader")[1]), None))
def every_label():
    labels, misses = doc["labels"], []
    for i, label in enumerate(labels):
        other = labels[(i + 1) % len(labels)]
        for q in (f"show me {label}", f"show me {label} and {other}"):
            if KEY not in keys(search(q)[1]):
                misses.append(q)
    return not misses, f"{2 * len(labels) - len(misses)}/{2 * len(labels)} queries" + (f", missed {misses}" if misses else "")
check("AC4", "every label finds the photo, alone and in pairs", every_label)
check("AC5", "result links open the photo", lambda: (
    http("GET", search(f"show me {TAG}")[1][0]["url"])[0] == 200, None))

print(f"\n{sum(results)}/{len(results)} checks passed")
