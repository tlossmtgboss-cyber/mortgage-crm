#!/usr/bin/env python3
"""Create LiveKit SIP dispatch rule for inbound calls.

Without a dispatch rule, LiveKit returns SIP 404 for all inbound calls —
it has the trunk but doesn't know what room/agent to dispatch to.

Usage:
  .venv/bin/python3 backend/scripts/setup_livekit_sip_dispatch.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from livekit import api as livekit_api


INBOUND_TRUNK_ID = os.getenv("LIVEKIT_SIP_INBOUND_TRUNK_ID", "ST_LQeRpHHAK7Bv")


async def main():
    lk = livekit_api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    # List existing dispatch rules
    print("=== Existing SIP Dispatch Rules ===")
    rules_resp = await lk.sip.list_sip_dispatch_rule(
        livekit_api.ListSIPDispatchRuleRequest()
    )
    if rules_resp.items:
        for rule in rules_resp.items:
            print(f"  ID: {rule.sip_dispatch_rule_id}")
            print(f"  Name: {rule.name}")
            print(f"  Trunks: {rule.trunk_ids}")
            print(f"  Rule: {rule.rule}")
            print()
    else:
        print("  (none)")
    print()

    # List inbound trunks for reference
    print("=== Existing SIP Inbound Trunks ===")
    trunks_resp = await lk.sip.list_sip_inbound_trunk(
        livekit_api.ListSIPInboundTrunkRequest()
    )
    if trunks_resp.items:
        for trunk in trunks_resp.items:
            print(f"  ID: {trunk.sip_trunk_id}")
            print(f"  Name: {trunk.name}")
            print(f"  Numbers: {trunk.numbers}")
            print(f"  Allowed IPs: {trunk.allowed_addresses}")
            print()
    else:
        print("  (none)")
    print()

    # Create dispatch rule for inbound calls
    print(f"=== Creating Dispatch Rule for trunk {INBOUND_TRUNK_ID} ===")
    try:
        dispatch_resp = await lk.sip.create_sip_dispatch_rule(
            livekit_api.CreateSIPDispatchRuleRequest(
                rule=livekit_api.SIPDispatchRule(
                    dispatch_rule_individual=livekit_api.SIPDispatchRuleIndividual(
                        room_prefix="aria-inbound-",
                        pin="",
                    )
                ),
                trunk_ids=[INBOUND_TRUNK_ID],
                name="Aria Inbound Calls",
            )
        )
        print(f"  Created! ID: {dispatch_resp.sip_dispatch_rule_id}")
        print(f"  Name: {dispatch_resp.name}")
        print(f"  Trunks: {dispatch_resp.trunk_ids}")
        print(f"  Rule: {dispatch_resp.rule}")
    except Exception as e:
        print(f"  ERROR: {e}")

    await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
