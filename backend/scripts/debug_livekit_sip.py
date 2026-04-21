#!/usr/bin/env python3
"""Debug LiveKit SIP configuration — check trunks, dispatch rules, rooms, and agents."""

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

    # 1. Inbound trunks
    print("=== SIP Inbound Trunks ===")
    trunks = await lk.sip.list_inbound_trunk(livekit_api.ListSIPInboundTrunkRequest())
    for t in trunks.items:
        print(f"  {t.sip_trunk_id}: name={t.name}")
        print(f"    numbers={t.numbers}")
        print(f"    allowed_addresses={t.allowed_addresses}")
        print(f"    allowed_numbers={t.allowed_numbers}")
        print(f"    metadata={t.metadata}")
        # Check all fields
        for field in ['headers', 'headers_to_attributes', 'krisp_enabled']:
            val = getattr(t, field, None)
            if val:
                print(f"    {field}={val}")
    print()

    # 2. Outbound trunks
    print("=== SIP Outbound Trunks ===")
    out_trunks = await lk.sip.list_outbound_trunk(livekit_api.ListSIPOutboundTrunkRequest())
    for t in out_trunks.items:
        print(f"  {t.sip_trunk_id}: name={t.name}")
        print(f"    address={t.address}")
        print(f"    numbers={t.numbers}")
        print(f"    transport={t.transport}")
        print(f"    auth_username={t.auth_username}")
    print()

    # 3. Dispatch rules
    print("=== SIP Dispatch Rules ===")
    rules = await lk.sip.list_dispatch_rule(livekit_api.ListSIPDispatchRuleRequest())
    for r in rules.items:
        print(f"  {r.sip_dispatch_rule_id}: name={r.name}")
        print(f"    trunk_ids={r.trunk_ids}")
        print(f"    rule={r.rule}")
        print(f"    metadata={r.metadata}")
        print(f"    attributes={r.attributes}")
        # Check for agent_name or hide_phone_number
        for field in dir(r):
            if not field.startswith('_') and field not in ('name', 'trunk_ids', 'rule', 'metadata', 'attributes', 'sip_dispatch_rule_id'):
                val = getattr(r, field, None)
                if val and not callable(val):
                    print(f"    {field}={val}")
    print()

    # 4. Active rooms
    print("=== Active Rooms ===")
    rooms = await lk.room.list_rooms(livekit_api.ListRoomsRequest())
    if rooms.rooms:
        for rm in rooms.rooms:
            print(f"  {rm.name}: participants={rm.num_participants}, metadata={rm.metadata[:100] if rm.metadata else 'none'}")
    else:
        print("  (no active rooms)")
    print()

    # 5. Check if agent workers are registered
    print("=== Agent Dispatches (recent) ===")
    try:
        dispatches = await lk.agent_dispatch.list_dispatch(
            livekit_api.ListAgentDispatchRequest(room="")
        )
        if dispatches.agent_dispatches:
            for d in dispatches.agent_dispatches:
                print(f"  {d.dispatch_id}: agent={d.agent_name}, room={d.room}")
        else:
            print("  (no dispatches)")
    except Exception as e:
        print(f"  Error listing dispatches: {e}")
    print()

    # 6. Check the dispatch rule details more carefully
    print("=== Dispatch Rule Detail ===")
    for r in rules.items:
        rule = r.rule
        print(f"  Rule type fields:")
        for field in dir(rule):
            if not field.startswith('_'):
                val = getattr(rule, field, None)
                if val and not callable(val):
                    print(f"    {field} = {val}")
    print()

    # 7. Try to get the inbound trunk detail
    print("=== Inbound Trunk Detail ===")
    for t in trunks.items:
        try:
            detail = await lk.sip.get_inbound_trunk(
                livekit_api.GetSIPInboundTrunkRequest(sip_trunk_id=t.sip_trunk_id)
            )
            trunk = detail.trunk
            print(f"  {trunk.sip_trunk_id}:")
            for field in dir(trunk):
                if not field.startswith('_'):
                    val = getattr(trunk, field, None)
                    if val and not callable(val):
                        print(f"    {field} = {val}")
        except Exception as e:
            print(f"  Error: {e}")

    await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
