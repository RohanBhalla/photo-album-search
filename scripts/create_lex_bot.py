"""Create or update the Lex V2 bot described in lex/bot.json. Safe to run again.

Steps: bot -> en_US locale -> slot type -> intent -> slots -> utterances
       -> build -> new version -> point the "prod" alias at it.
Prints the bot id and alias id to put in .env.
Usage: .venv/bin/python scripts/create_lex_bot.py
"""
import json
import pathlib
import time

import boto3

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = json.loads((ROOT / "lex" / "bot.json").read_text())
session = boto3.Session(profile_name="cc-hw1", region_name="us-east-1")
lex = session.client("lexv2-models")
iam = session.client("iam")
L = spec["locale"]
D = {"botVersion": "DRAFT", "localeId": L}
ALIAS = "prod"
SLOT_PROMPT = {
    "slotConstraint": "Optional",  # never ask follow-up questions; LF2 just reads what was found
    "promptSpecification": {
        "messageGroups": [{"message": {"plainTextMessage": {"value": "What would you like to search for?"}}}],
        "maxRetries": 1,
    },
}


def wait(fn, field, done, **kw):
    while True:
        try:
            status = fn(**kw)[field]
        except lex.exceptions.ResourceNotFoundException:  # async create not visible yet
            time.sleep(5)
            continue
        if status in done:
            return status
        if "Failed" in status:
            raise RuntimeError(f"{fn.__name__}: {status}")
        time.sleep(5)


def find(items, name_key, name, id_key):
    return next((i[id_key] for i in items if i[name_key] == name), None)


# --- bot -------------------------------------------------------------------
bot_id = find(lex.list_bots()["botSummaries"], "botName", spec["botName"], "botId")
if not bot_id:
    try:
        iam.create_service_linked_role(AWSServiceName="lexv2.amazonaws.com", CustomSuffix=spec["botName"])
        time.sleep(10)
    except iam.exceptions.InvalidInputException:
        pass  # role already exists
    role_arn = iam.get_role(RoleName=f"AWSServiceRoleForLexV2Bots_{spec['botName']}")["Role"]["Arn"]
    bot_id = lex.create_bot(
        botName=spec["botName"], roleArn=role_arn, idleSessionTTLInSeconds=300,
        description="Pulls search keywords out of photo search queries",
        dataPrivacy={"childDirected": False},
    )["botId"]
    wait(lex.describe_bot, "botStatus", {"Available"}, botId=bot_id)
    lex.create_bot_locale(botId=bot_id, nluIntentConfidenceThreshold=0.40, **D)
wait(lex.describe_bot_locale, "botLocaleStatus", {"NotBuilt", "Built", "ReadyExpressTesting"}, botId=bot_id, **D)

# --- slot type: accepts ANY value (OriginalValue); examples teach Lex what keywords look like
slot_type_args = dict(
    botId=bot_id, slotTypeName=spec["slotTypeName"],
    valueSelectionSetting={"resolutionStrategy": "OriginalValue"},
    slotTypeValues=[{"sampleValue": {"value": v}} for v in spec["slotTypeExamples"]], **D,
)
slot_type_id = find(lex.list_slot_types(botId=bot_id, **D)["slotTypeSummaries"],
                    "slotTypeName", spec["slotTypeName"], "slotTypeId")
if slot_type_id:
    lex.update_slot_type(slotTypeId=slot_type_id, **slot_type_args)
else:
    slot_type_id = lex.create_slot_type(**slot_type_args)["slotTypeId"]

# --- intent + slots ---------------------------------------------------------
intent_id = find(lex.list_intents(botId=bot_id, **D)["intentSummaries"],
                 "intentName", spec["intentName"], "intentId")
if not intent_id:
    intent_id = lex.create_intent(botId=bot_id, intentName=spec["intentName"], **D)["intentId"]

existing_slots = {s["slotName"]: s["slotId"]
                  for s in lex.list_slots(botId=bot_id, intentId=intent_id, **D)["slotSummaries"]}
slot_ids = []
for name in spec["slots"]:
    if name in existing_slots:
        slot_ids.append(existing_slots[name])
    else:
        slot_ids.append(lex.create_slot(botId=bot_id, intentId=intent_id, slotName=name,
                                        slotTypeId=slot_type_id, valueElicitationSetting=SLOT_PROMPT,
                                        **D)["slotId"])

lex.update_intent(
    botId=bot_id, intentId=intent_id, intentName=spec["intentName"],
    description="Search photos by one or two keywords",
    sampleUtterances=[{"utterance": u} for u in spec["utterances"]],
    slotPriorities=[{"priority": i + 1, "slotId": s} for i, s in enumerate(slot_ids)], **D,
)

# --- build, version, alias --------------------------------------------------
lex.build_bot_locale(botId=bot_id, **D)
wait(lex.describe_bot_locale, "botLocaleStatus", {"Built"}, botId=bot_id, **D)

version = lex.create_bot_version(
    botId=bot_id, botVersionLocaleSpecification={L: {"sourceBotVersion": "DRAFT"}}
)["botVersion"]
wait(lex.describe_bot_version, "botStatus", {"Available"}, botId=bot_id, botVersion=version)

alias_args = dict(botId=bot_id, botAliasName=ALIAS, botVersion=version,
                  botAliasLocaleSettings={L: {"enabled": True}})
alias_id = find(lex.list_bot_aliases(botId=bot_id)["botAliasSummaries"], "botAliasName", ALIAS, "botAliasId")
if alias_id:
    lex.update_bot_alias(botAliasId=alias_id, **alias_args)
else:
    alias_id = lex.create_bot_alias(**alias_args)["botAliasId"]
wait(lex.describe_bot_alias, "botAliasStatus", {"Available"}, botId=bot_id, botAliasId=alias_id)

print(json.dumps({"LEX_BOT_ID": bot_id, "LEX_BOT_ALIAS_ID": alias_id, "version": version}))
