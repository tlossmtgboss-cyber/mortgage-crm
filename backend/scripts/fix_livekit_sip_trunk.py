#!/usr/bin/env python3
"""Debug and fix LiveKit SIP trunk — try different number formats and trunk configs."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from livekit import api as livekit_api


async def main():
    lk = livekit_api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    # 1. Delete existing dispatch rule and trunk
    print("=== Step 1: Cleaning up existing config ===")

    rules = await lk.sip.list_dispatch_rule(livekit_api.ListSIPDispatchRuleRequest())
    for r in rules.items:
        print(f"  Deleting dispatch rule: {r.sip_dispatch_rule_id} ({r.name})")
        await lk.sip.delete_dispatch_rule(
            livekit_api.DeleteSIPDispatchRuleRequest(
                sip_dispatch_rule_id=r.sip_dispatch_rule_id
            )
        )

    trunks = await lk.sip.list_inbound_trunk(livekit_api.ListSIPInboundTrunkRequest())
    for t in trunks.items:
        print(f"  Deleting inbound trunk: {t.sip_trunk_id} ({t.name})")
        await lk.sip.delete_sip_trunk(
            livekit_api.DeleteSIPTrunkRequest(sip_trunk_id=t.sip_trunk_id)
        )
    print()

    # 2. Create new inbound trunk with auth disabled, wildcard config
    print("=== Step 2: Creating new inbound trunk ===")
    new_trunk = await lk.sip.create_sip_inbound_trunk(
        livekit_api.CreateSIPInboundTrunkRequest(
            trunk=livekit_api.SIPInboundTrunkInfo(
                name="Telnyx Inbound",
                numbers=["+18438838956"],
                allowed_addresses=["0.0.0.0/0"],
                allowed_numbers=[],
            )
        )
    )
    trunk_id = new_trunk.sip_trunk_id
    print(f"  Created trunk: {trunk_id}")
    print(f"    numbers: {new_trunk.numbers}")
    print(f"    allowed_addresses: {new_trunk.allowed_addresses}")
    print()

    # 3. Create dispatch rule with agent_name
    print("=== Step 3: Creating dispatch rule ===")
    new_rule = await lk.sip.create_dispatch_rule(
        livekit_api.CreateSIPDispatchRuleRequest(
            rule=livekit_api.SIPDispatchRule(
                dispatch_rule_individual=livekit_api.SIPDispatchRuleIndividual(
                    room_prefix="aria-inbound-",
                    pin="",
                )
            ),
            trunk_ids=[trunk_id],
            name="Aria Inbound Calls",
            metadata='{"agent": "aria-voice"}',
        )
    )
    print(f"  Created rule: {new_rule.sip_dispatch_rule_id}")
    print(f"    trunk_ids: {new_rule.trunk_ids}")
    print(f"    rule: {new_rule.rule}")
    print()

    # 4. Verify final state
    print("=== Final State ===")
    trunks2 = await lk.sip.list_inbound_trunk(livekit_api.ListSIPInboundTrunkRequest())
    for t in trunks2.items:
        print(f"  Trunk: {t.sip_trunk_id} numbers={t.numbers} allowed={t.allowed_addresses}")

    rules2 = await lk.sip.list_dispatch_rule(livekit_api.ListSIPDispatchRuleRequest())
    for r in rules2.items:
        print(f"  Rule: {r.sip_dispatch_rule_id} trunks={r.trunk_ids} rule={r.rule}")

    await lk.aclose()
    print("\nDone. Try calling +18438838956 now.")


if __name__ == "__main__":
    asyncio.run(main())
