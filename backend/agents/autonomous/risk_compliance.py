"""
Risk & Compliance Agents

Autonomous agents focused on regulatory compliance and risk detection:
1. wire_fraud_scanner — Every 15 min, scan for suspicious email/wire patterns
2. ecoa_audit — Daily, verify no prohibited questions in AI conversations
3. tcpa_compliance_scanner — Daily, verify quiet hours and opt-outs respected
4. hmda_data_collector — Daily, ensure HMDA reportable fields are complete
5. fair_lending_monitor — Weekly, statistical analysis of lending patterns
"""

import logging
import math
import re
from typing import Any, Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

TERMINAL_STAGES = (
    "'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'"
)

# US state -> IANA timezone (TCPA quiet-hours enforcement)
_STATE_TIMEZONE = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "HI": "Pacific/Honolulu", "ID": "America/Boise",
    "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/New_York",
    "LA": "America/Chicago", "ME": "America/New_York", "MD": "America/New_York",
    "MA": "America/New_York", "MI": "America/Detroit", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver",
    "NE": "America/Chicago", "NV": "America/Los_Angeles", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver", "NY": "America/New_York",
    "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "SD": "America/Chicago",
    "TN": "America/Chicago", "TX": "America/Chicago", "UT": "America/Denver",
    "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver",
    "DC": "America/New_York",
}


def _utc_offset_hours(tz_name: str) -> int:
    """Rough UTC offset for a US timezone (no DST — conservative for compliance)."""
    offsets = {
        "America/New_York": -5, "America/Chicago": -6, "America/Denver": -7,
        "America/Los_Angeles": -8, "America/Anchorage": -9, "Pacific/Honolulu": -10,
        "America/Phoenix": -7, "America/Boise": -7, "America/Detroit": -5,
        "America/Indiana/Indianapolis": -5,
    }
    return offsets.get(tz_name, -5)


def _extract_state_from_address(address: str) -> str | None:
    """Extract 2-letter US state from an address string."""
    if not address:
        return None
    # Match "State ZIP" or ", ST " pattern
    m = re.search(r',?\s+([A-Z]{2})\s+\d{5}', address)
    if m:
        return m.group(1)
    # Match 2-letter state code at end
    m = re.search(r'\b([A-Z]{2})$', address.strip())
    if m and m.group(1) in _STATE_TIMEZONE:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 1. Wire Fraud Scanner
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="wire_fraud_scanner",
    description="Scan for suspicious wire/email patterns indicating fraud attempts",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def wire_fraud_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Detect emails with wire instruction changes, domain spoofing, and
    urgency-language patterns that indicate potential wire fraud."""
    actions = 0
    false_positives_suppressed = 0
    fraud_indicators_found: List[Dict[str, Any]] = []

    # -- Known title company / lender domains for this org ----------------
    # Pull verified domains from loan records (title_company field + lender)
    verified_domains_rows = db.execute(text("""
        SELECT DISTINCT
            LOWER(TRIM(l.title_company)) as entity,
            LOWER(TRIM(SPLIT_PART(l.borrower_email, '@', 2))) as domain
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.title_company IS NOT NULL
          AND l.borrower_email IS NOT NULL
          AND l.stage NOT IN (""" + TERMINAL_STAGES + """)
        UNION
        SELECT DISTINCT
            LOWER(TRIM(l.lender)) as entity,
            LOWER(TRIM(SPLIT_PART(l.loan_officer_email, '@', 2))) as domain
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lender IS NOT NULL
          AND l.loan_officer_email IS NOT NULL
          AND l.stage NOT IN (""" + TERMINAL_STAGES + """)
    """), {"org_id": organization_id}).fetchall()
    verified_domains = {row[1] for row in verified_domains_rows if row[1]}

    # -- Wire instruction keyword scan ------------------------------------
    # Primary patterns: explicit wire changes
    wire_change_rows = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) as responsible_user_id,
               COALESCE(ln.borrower_name, CONCAT(l.first_name, ' ', l.last_name)) as contact_name
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        LEFT JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
          AND a.type IN ('Email', 'System', 'Note')
          AND (
              LOWER(a.content) LIKE '%wire%instruct%'
              OR LOWER(a.content) LIKE '%routing%number%changed%'
              OR LOWER(a.content) LIKE '%new%bank%account%'
              OR LOWER(a.content) LIKE '%updated%closing%account%'
              OR LOWER(a.content) LIKE '%send%funds%to%'
              OR LOWER(a.content) LIKE '%wiring%details%changed%'
              OR LOWER(a.content) LIKE '%account%number%updated%'
              OR LOWER(a.content) LIKE '%transfer%immediately%'
          )
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    # -- Urgency-language patterns ----------------------------------------
    urgency_rows = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) as responsible_user_id,
               COALESCE(ln.borrower_name, CONCAT(l.first_name, ' ', l.last_name)) as contact_name
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        LEFT JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
          AND a.type = 'Email'
          AND (
              LOWER(a.content) LIKE '%wire immediately%'
              OR LOWER(a.content) LIKE '%closing today%must wire%'
              OR LOWER(a.content) LIKE '%account changed%'
              OR LOWER(a.content) LIKE '%urgent%wire%'
              OR LOWER(a.content) LIKE '%time sensitive%fund%'
              OR LOWER(a.content) LIKE '%do not delay%'
              OR LOWER(a.content) LIKE '%must send today%'
          )
        LIMIT 30
    """), {"org_id": organization_id}).fetchall()

    # -- After-hours urgency check ----------------------------------------
    after_hours_urgent = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) as responsible_user_id,
               COALESCE(ln.borrower_name, CONCAT(l.first_name, ' ', l.last_name)) as contact_name
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        LEFT JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
          AND a.type = 'Email'
          AND (EXTRACT(HOUR FROM a.created_at AT TIME ZONE :tz) < 7
               OR EXTRACT(HOUR FROM a.created_at AT TIME ZONE :tz) >= 20)
          AND (
              LOWER(a.content) LIKE '%wire%' OR LOWER(a.content) LIKE '%closing%'
              OR LOWER(a.content) LIKE '%funds%'
          )
        LIMIT 20
    """), {"org_id": organization_id, "tz": org_timezone}).fetchall()

    # -- Deduplicate and merge all suspicious activities ------------------
    seen_activity_ids: set = set()
    all_suspicious: List[Tuple] = []
    indicator_labels: Dict[int, List[str]] = {}

    for row in wire_change_rows:
        aid = row[0]
        if aid not in seen_activity_ids:
            seen_activity_ids.add(aid)
            all_suspicious.append(row)
            indicator_labels.setdefault(aid, []).append("WIRE_INSTRUCTION_CHANGE")

    for row in urgency_rows:
        aid = row[0]
        if aid not in seen_activity_ids:
            seen_activity_ids.add(aid)
            all_suspicious.append(row)
        indicator_labels.setdefault(aid, []).append("URGENCY_LANGUAGE")

    for row in after_hours_urgent:
        aid = row[0]
        if aid not in seen_activity_ids:
            seen_activity_ids.add(aid)
            all_suspicious.append(row)
        indicator_labels.setdefault(aid, []).append("AFTER_HOURS_URGENCY")

    # -- Domain spoofing check on email activities -------------------------
    for row in all_suspicious:
        content_lower = str(row[3] or "").lower()
        # Attempt to extract sender domain from content (e.g., "From: user@domain.com")
        domain_match = re.search(r'from[:\s]+\S+@([\w.-]+)', content_lower)
        if domain_match and verified_domains:
            sender_domain = domain_match.group(1)
            # Check for typosquatting: domain similar to but not matching verified domains
            for vd in verified_domains:
                if not vd:
                    continue
                if sender_domain != vd and _domains_similar(sender_domain, vd):
                    indicator_labels.setdefault(row[0], []).append(
                        f"DOMAIN_SPOOF ('{sender_domain}' looks like '{vd}')"
                    )
                    break

    # -- Create compliance alerts for each suspicious activity ------------
    for row in all_suspicious:
        activity_id = row[0]
        lead_id = row[1]
        loan_id = row[2]
        content_snippet = str(row[3] or "")[:300]
        responsible_user = row[5]
        contact_name = row[6] or "Unknown"
        indicators = indicator_labels.get(activity_id, ["SUSPICIOUS_CONTENT"])

        # Dedup: skip if alert already exists for this activity in last 24h
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id AND alert_type = 'WIRE_FRAUD_SUSPECT'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"org_id": organization_id, "pattern": f"%activity_id={activity_id}%"}).fetchone()

        if existing:
            false_positives_suppressed += 1
            continue

        severity = "critical" if "WIRE_INSTRUCTION_CHANGE" in indicators or any(
            "DOMAIN_SPOOF" in i for i in indicators
        ) else "high"

        indicator_str = ", ".join(indicators)
        description = (
            f"WIRE FRAUD ALERT | activity_id={activity_id} | Contact: {contact_name}\n"
            f"Fraud indicators: {indicator_str}\n"
            f"Content: {content_snippet}\n\n"
            f"RECOMMENDED ACTION: Do NOT wire funds. Call the title company at their "
            f"verified phone number to confirm any wire instruction changes. Never rely "
            f"on contact information provided in the suspicious email."
        )

        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, lead_id, organization_id, alert_type, severity, title,
                 description, status, created_at)
            VALUES
                (:loan_id, :lead_id, :org_id, 'WIRE_FRAUD_SUSPECT', :severity,
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "loan_id": loan_id,
            "lead_id": lead_id,
            "org_id": organization_id,
            "severity": severity,
            "title": f"Wire fraud alert: {indicator_str} — {contact_name}",
            "desc": description,
        })

        # Audit trail: log activity on the loan/lead record
        db.execute(text("""
            INSERT INTO activities (lead_id, loan_id, type, content, created_at, organization_id)
            VALUES (:lead_id, :loan_id, 'Note', :content, CURRENT_TIMESTAMP, :org_id)
        """), {
            "lead_id": lead_id,
            "loan_id": loan_id,
            "content": f"[WIRE FRAUD SCANNER] Alert created — indicators: {indicator_str}. "
                       f"Do NOT wire funds without verbal verification.",
            "org_id": organization_id,
        })

        fraud_indicators_found.append({
            "activity_id": activity_id,
            "indicators": indicators,
            "severity": severity,
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Wire fraud scanner commit failed: {e}")

    return {
        "summary": f"{actions} wire fraud alerts created, {false_positives_suppressed} deduped",
        "actions_taken": actions,
        "notifications_sent": 0,
        "fraud_indicators": fraud_indicators_found,
        "false_positives_suppressed": false_positives_suppressed,
        "verified_domains_count": len(verified_domains),
    }


def _domains_similar(a: str, b: str) -> bool:
    """Basic typosquat detector: Levenshtein distance <= 2 and length within 3."""
    if abs(len(a) - len(b)) > 3:
        return False
    # Simple edit distance (Levenshtein) with early exit
    if a == b:
        return False  # Exact match is not spoofing
    la, lb = len(a), len(b)
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    prev = list(range(la + 1))
    for j in range(1, lb + 1):
        curr = [j] + [0] * la
        for i in range(1, la + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(curr[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost)
        prev = curr
    return 0 < prev[la] <= 2


# ---------------------------------------------------------------------------
# 2. ECOA Audit Agent
# ---------------------------------------------------------------------------

# Prohibited patterns organized by ECOA category
_ECOA_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "race_ethnicity": {
        "patterns": [
            r"\brace\b", r"\bethnicit", r"\bethnic\b", r"\bhispanic\b",
            r"\blatino\b", r"\bcaucasian\b", r"\bafrican.?american\b",
            r"\basian\b(?!.*pacific.*mortgage)", r"\bwhite\b(?!.*pages|.*paper)",
            r"\bblack\b(?!.*list|.*out|.*stone)",
        ],
        "severity": "critical",
    },
    "sex_gender": {
        "patterns": [
            r"what.{0,10}gender", r"are you (?:male|female)", r"\bsex\b(?!.*offend)",
            r"\bpregnant\b", r"\bpregnancy\b",
        ],
        "severity": "critical",
    },
    "religion": {
        "patterns": [
            r"what.{0,10}religion", r"are you (?:christian|muslim|jewish|hindu|buddhist)",
            r"\breligious\b(?!.*holiday)", r"what church",
        ],
        "severity": "critical",
    },
    "national_origin": {
        "patterns": [
            r"(?:where|what country).{0,15}(?:from|born|citizen)",
            r"\bnational origin\b", r"\bimmigr(?:ant|ation)\b(?!.*visa.*status)",
            r"are you.{0,10}american", r"\bcitizenship\b(?!.*status.*verified)",
        ],
        "severity": "critical",
    },
    "age": {
        "patterns": [
            r"how old are you", r"what(?:'s| is) your age", r"\byour age\b",
            r"date of birth(?!.*verify|.*confirm|.*application)",
            r"when were you born(?!.*verify)",
        ],
        "severity": "high",
    },
    "marital_status": {
        "patterns": [
            r"are you married", r"marital status(?!.*on.*application)",
            r"are you (?:single|divorced|separated|widowed)",
            r"\bspouse\b(?!.*co.?borrower|.*income|.*on.*loan)",
        ],
        "severity": "high",
    },
    "familial_status": {
        "patterns": [
            r"(?:do you|how many).{0,10}(?:children|kids)",
            r"are you.{0,10}(?:expecting|pregnant)",
            r"\bfamilial status\b", r"planning.{0,10}family",
        ],
        "severity": "high",
    },
    "disability": {
        "patterns": [
            r"(?:do you|are you).{0,15}(?:disabled|handicap|disability)",
            r"\bphysical.{0,10}limitation\b", r"\bmental.{0,10}(?:illness|condition)\b",
        ],
        "severity": "critical",
    },
}


@autonomous_agent(
    name="ecoa_audit",
    description="Verify no prohibited questions (race, sex, religion) in AI conversations",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=120,
)
def ecoa_audit(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Scan AI conversations and call transcript activities for ECOA-prohibited
    topics. Categorize by violation type, score severity, and track repeat
    offenders."""
    actions = 0
    violations_by_category: Dict[str, int] = {}
    repeat_offenders: Dict[int, int] = {}  # user_id -> count

    # ---- Scan conversations table (AI chat) -----------------------------
    conversations = db.execute(text("""
        SELECT c.id, c.user_id, c.message, c.response, c.created_at
        FROM conversations c
        WHERE c.organization_id = :org_id
          AND c.created_at >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY c.created_at DESC
        LIMIT 500
    """), {"org_id": organization_id}).fetchall()

    # ---- Scan agent_conversations summaries -----------------------------
    agent_convos = db.execute(text("""
        SELECT ac.id, ac.user_id, ac.summary, ac.key_points, ac.started_at
        FROM agent_conversations ac
        WHERE ac.organization_id = :org_id
          AND ac.started_at >= CURRENT_DATE - INTERVAL '1 day'
          AND ac.summary IS NOT NULL
        ORDER BY ac.started_at DESC
        LIMIT 200
    """), {"org_id": organization_id}).fetchall()

    # ---- Scan activities for call transcripts and notes -----------------
    call_activities = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) as user_id
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        LEFT JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('Call', 'Note', 'Meeting')
          AND LENGTH(a.content) > 50
        ORDER BY a.created_at DESC
        LIMIT 300
    """), {"org_id": organization_id}).fetchall()

    # Combine all scannable text segments: (source_type, source_id, user_id, text, is_ai_response)
    text_segments: List[Tuple[str, int, int | None, str, bool]] = []

    for row in conversations:
        cid, user_id, message, response = row[0], row[1], row[2], row[3]
        if message:
            text_segments.append(("conversation", cid, user_id, message, False))
        if response:
            text_segments.append(("conversation", cid, user_id, response, True))

    for row in agent_convos:
        acid, user_id, summary = row[0], row[1], row[2]
        if summary:
            text_segments.append(("agent_conversation", acid, user_id, summary, True))
        # key_points is JSON — scan string representation
        if row[3]:
            kp_str = str(row[3])
            if len(kp_str) > 10:
                text_segments.append(("agent_conversation", acid, user_id, kp_str, True))

    for row in call_activities:
        aid, lead_id, loan_id, content, _, user_id = row
        if content:
            text_segments.append(("activity", aid, user_id, content, False))

    # ---- Pattern matching across all text segments ----------------------
    # Collect unique violations for dedup: (source_type, source_id, category)
    found_violations: List[Dict[str, Any]] = []
    dedup_set: set = set()

    for source_type, source_id, user_id, content, is_ai_response in text_segments:
        content_lower = content.lower()
        for category, cfg in _ECOA_CATEGORIES.items():
            for pattern in cfg["patterns"]:
                if re.search(pattern, content_lower):
                    dedup_key = (source_type, source_id, category)
                    if dedup_key in dedup_set:
                        break
                    dedup_set.add(dedup_key)

                    # AI response violations are more severe (system should prevent)
                    severity = cfg["severity"]
                    if is_ai_response and severity == "high":
                        severity = "critical"

                    source_label = "AI response" if is_ai_response else "LO message/transcript"

                    found_violations.append({
                        "source_type": source_type,
                        "source_id": source_id,
                        "user_id": user_id,
                        "category": category,
                        "severity": severity,
                        "source_label": source_label,
                        "snippet": content[:200],
                        "matched_pattern": pattern,
                    })
                    violations_by_category[category] = violations_by_category.get(category, 0) + 1
                    if user_id:
                        repeat_offenders[user_id] = repeat_offenders.get(user_id, 0) + 1
                    break  # One match per category per segment

    # ---- Check repeat offender history ----------------------------------
    repeat_offender_users: Dict[int, int] = {}
    for user_id in repeat_offenders:
        if not user_id:
            continue
        prior_count = db.execute(text("""
            SELECT COUNT(*) FROM compliance_alerts
            WHERE organization_id = :org_id
              AND alert_type = 'ECOA_VIOLATION'
              AND description LIKE :user_pattern
              AND created_at >= CURRENT_DATE - INTERVAL '90 days'
        """), {
            "org_id": organization_id,
            "user_pattern": f"%user_id={user_id}%",
        }).scalar() or 0
        if prior_count > 0:
            repeat_offender_users[user_id] = prior_count

    # ---- Create alerts and remediation tasks ----------------------------
    for v in found_violations:
        # Dedup against existing alerts in last 24h
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id AND alert_type = 'ECOA_VIOLATION'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {
            "org_id": organization_id,
            "pattern": f"%{v['source_type']}={v['source_id']}%{v['category']}%",
        }).fetchone()

        if existing:
            continue

        prior_offenses = repeat_offender_users.get(v["user_id"], 0)
        repeat_note = (
            f" REPEAT OFFENDER: {prior_offenses} prior ECOA alerts in 90 days."
            if prior_offenses > 0 else ""
        )

        description = (
            f"ECOA violation detected | {v['source_type']}={v['source_id']} | "
            f"user_id={v['user_id']}\n"
            f"Category: {v['category'].replace('_', ' ').title()}\n"
            f"Source: {v['source_label']}\n"
            f"Severity: {v['severity']}\n"
            f"Snippet: {v['snippet']}\n"
            f"Pattern matched: {v['matched_pattern']}{repeat_note}\n\n"
            f"ECOA (Regulation B, 12 CFR 1002) prohibits inquiries about protected "
            f"characteristics. Review and retrain."
        )

        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, organization_id, alert_type, severity, title,
                 description, status, created_at)
            VALUES
                (NULL, :org_id, 'ECOA_VIOLATION', :severity,
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "org_id": organization_id,
            "severity": v["severity"],
            "title": f"ECOA: {v['category'].replace('_', ' ').title()} — {v['source_label']}",
            "desc": description,
        })
        actions += 1

        # Create remediation task for the LO if user_id is known
        if v["user_id"]:
            training_resources = {
                "race_ethnicity": "ECOA Fair Lending Training Module 1: Race & Ethnicity",
                "sex_gender": "ECOA Fair Lending Training Module 2: Gender & Sex Discrimination",
                "religion": "ECOA Fair Lending Training Module 3: Religious Discrimination",
                "national_origin": "ECOA Fair Lending Training Module 4: National Origin",
                "age": "ECOA Fair Lending Training Module 5: Age Discrimination (Reg B)",
                "marital_status": "ECOA Fair Lending Training Module 6: Marital Status",
                "familial_status": "Fair Housing Training Module: Familial Status",
                "disability": "Fair Housing Training Module: Disability Accommodations",
            }
            resource = training_resources.get(v["category"], "ECOA General Compliance Training")

            # Only create task if one doesn't exist for this user+category recently
            existing_task = db.execute(text("""
                SELECT id FROM tasks
                WHERE organization_id = :org_id AND owner_id = :user_id
                  AND title LIKE :pattern
                  AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
                LIMIT 1
            """), {
                "org_id": organization_id,
                "user_id": str(v["user_id"]),
                "pattern": f"%ECOA%{v['category']}%",
            }).fetchone()

            if not existing_task:
                priority = "high" if prior_offenses > 0 else "medium"
                db.execute(text("""
                    INSERT INTO tasks
                        (title, description, owner_id, priority, status,
                         due_date, created_at, organization_id)
                    VALUES
                        (:title, :desc, :owner_id, :priority, 'pending',
                         CURRENT_DATE + 3, CURRENT_TIMESTAMP, :org_id)
                """), {
                    "title": f"ECOA remediation: {v['category'].replace('_', ' ')} training required",
                    "desc": (
                        f"An ECOA compliance scan detected a potential {v['category'].replace('_', ' ')} "
                        f"violation. Complete required training: {resource}. "
                        f"{'This is a repeat finding — escalation may follow.' if prior_offenses > 0 else ''}"
                    ),
                    "owner_id": str(v["user_id"]),
                    "priority": priority,
                    "org_id": organization_id,
                })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"ECOA audit commit failed: {e}")

    return {
        "summary": f"{actions} ECOA alerts created across {len(violations_by_category)} categories",
        "actions_taken": actions,
        "notifications_sent": 0,
        "violations_by_category": violations_by_category,
        "repeat_offenders": {uid: cnt for uid, cnt in repeat_offender_users.items()},
        "segments_scanned": len(text_segments),
    }


# ---------------------------------------------------------------------------
# 3. TCPA Compliance Scanner
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="tcpa_compliance_scanner",
    description="Verify quiet hours and opt-out compliance for calls/SMS",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=90,
)
def tcpa_compliance_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Check calls/SMS against borrower timezone quiet hours, DNC lists,
    frequency caps, and consent requirements. Produce per-LO compliance
    scores."""
    actions = 0
    lo_violations: Dict[int, Dict[str, int]] = {}  # lo_id -> {type: count}

    # ---- 1. Quiet-hours by borrower timezone ----------------------------
    # Get all outbound contact activities with lead address/state info
    contacts_with_state = db.execute(text("""
        SELECT a.id, a.lead_id, a.type, a.created_at,
               l.owner_id as lo_id,
               COALESCE(l.state, '') as lead_state,
               CONCAT(l.first_name, ' ', l.last_name) as lead_name,
               l.phone as lead_phone
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('Call', 'SMS')
        ORDER BY a.created_at DESC
        LIMIT 500
    """), {"org_id": organization_id}).fetchall()

    # Also check loan-based contacts
    loan_contacts = db.execute(text("""
        SELECT a.id, a.loan_id, a.type, a.created_at,
               ln.loan_officer_id as lo_id,
               COALESCE(ln.property_state, '') as state,
               ln.borrower_name as contact_name,
               ln.borrower_phone as phone
        FROM activities a
        JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('Call', 'SMS')
        ORDER BY a.created_at DESC
        LIMIT 200
    """), {"org_id": organization_id}).fetchall()

    after_hours_violations: List[Dict[str, Any]] = []

    for row in contacts_with_state:
        activity_id, lead_id, act_type, created_at, lo_id = row[0], row[1], row[2], row[3], row[4]
        state_code = (row[5] or "").strip().upper()
        tz_name = _STATE_TIMEZONE.get(state_code, org_timezone)
        offset = _utc_offset_hours(tz_name)

        # Convert UTC activity time to borrower local hour (approximate)
        if created_at:
            local_hour = (created_at.hour + offset) % 24
            # TCPA: no calls/texts before 8am or after 9pm local time
            if local_hour < 8 or local_hour >= 21:
                after_hours_violations.append({
                    "activity_id": activity_id,
                    "lo_id": lo_id,
                    "type": str(act_type),
                    "local_hour": local_hour,
                    "state": state_code or "unknown",
                    "timezone": tz_name,
                    "contact_name": row[6] or "Unknown",
                })
                if lo_id:
                    lo_violations.setdefault(lo_id, {}).setdefault("quiet_hours", 0)
                    lo_violations[lo_id]["quiet_hours"] += 1

    for row in loan_contacts:
        activity_id, loan_id, act_type, created_at, lo_id = row[0], row[1], row[2], row[3], row[4]
        state_code = (row[5] or "").strip().upper()
        tz_name = _STATE_TIMEZONE.get(state_code, org_timezone)
        offset = _utc_offset_hours(tz_name)

        if created_at:
            local_hour = (created_at.hour + offset) % 24
            if local_hour < 8 or local_hour >= 21:
                after_hours_violations.append({
                    "activity_id": activity_id,
                    "lo_id": lo_id,
                    "type": str(act_type),
                    "local_hour": local_hour,
                    "state": state_code or "unknown",
                    "timezone": tz_name,
                    "contact_name": row[6] or "Unknown",
                })
                if lo_id:
                    lo_violations.setdefault(lo_id, {}).setdefault("quiet_hours", 0)
                    lo_violations[lo_id]["quiet_hours"] += 1

    # Create per-violation alerts for quiet hours
    for v in after_hours_violations[:20]:  # Cap at 20 individual alerts
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id AND alert_type = 'TCPA_QUIET_HOURS'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"org_id": organization_id, "pattern": f"%activity_id={v['activity_id']}%"}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, organization_id, alert_type, severity, title,
                     description, status, created_at)
                VALUES
                    (NULL, :org_id, 'TCPA_QUIET_HOURS', 'high',
                     :title, :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "org_id": organization_id,
                "title": f"TCPA quiet hours: {v['type']} at {v['local_hour']}:00 local ({v['state']})",
                "desc": (
                    f"activity_id={v['activity_id']} | {v['type']} to {v['contact_name']} "
                    f"at {v['local_hour']}:00 local time ({v['timezone']}). "
                    f"TCPA requires contacts only 8am-9pm in the recipient's timezone."
                ),
            })
            actions += 1

    # ---- 2. DNC / opt-out compliance ------------------------------------
    # Check sms_opt_outs table
    opted_out_sms = db.execute(text("""
        SELECT a.id, a.lead_id, l.phone, l.owner_id,
               CONCAT(l.first_name, ' ', l.last_name) as lead_name
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('SMS', 'Call')
          AND l.phone IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM sms_opt_outs so
              WHERE so.phone_number = l.phone AND so.active = true
          )
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    # Also check channel_preferences DNC flags
    dnc_contacts = db.execute(text("""
        SELECT a.id, a.lead_id, a.type, l.owner_id,
               CONCAT(l.first_name, ' ', l.last_name) as lead_name
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        JOIN channel_preferences cp ON cp.lead_id = l.id AND cp.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND (
              (a.type = 'SMS' AND cp.do_not_sms = true)
              OR (a.type = 'Call' AND cp.do_not_call = true)
          )
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    all_dnc_violations = []
    seen_dnc_aids: set = set()

    for row in opted_out_sms:
        aid = row[0]
        if aid not in seen_dnc_aids:
            seen_dnc_aids.add(aid)
            all_dnc_violations.append({
                "activity_id": aid, "lead_id": row[1], "lo_id": row[3],
                "lead_name": row[4], "source": "sms_opt_outs",
            })
            if row[3]:
                lo_violations.setdefault(row[3], {}).setdefault("dnc", 0)
                lo_violations[row[3]]["dnc"] += 1

    for row in dnc_contacts:
        aid = row[0]
        if aid not in seen_dnc_aids:
            seen_dnc_aids.add(aid)
            all_dnc_violations.append({
                "activity_id": aid, "lead_id": row[1], "lo_id": row[3],
                "lead_name": row[4], "source": "channel_preferences",
            })
            if row[3]:
                lo_violations.setdefault(row[3], {}).setdefault("dnc", 0)
                lo_violations[row[3]]["dnc"] += 1

    for v in all_dnc_violations:
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id AND alert_type = 'TCPA_OPT_OUT'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"org_id": organization_id, "pattern": f"%activity_id={v['activity_id']}%"}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, lead_id, organization_id, alert_type, severity, title,
                     description, status, created_at)
                VALUES
                    (NULL, :lead_id, :org_id, 'TCPA_OPT_OUT', 'critical',
                     :title, :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "lead_id": v["lead_id"],
                "org_id": organization_id,
                "title": f"TCPA: Contact to DNC/{v['source']} — {v['lead_name']}",
                "desc": (
                    f"activity_id={v['activity_id']} | Contact to {v['lead_name']} who is on "
                    f"the {v['source']} list. Source: {v['source']}. "
                    f"Immediate review required. TCPA penalties: $500-$1,500 per violation."
                ),
            })
            actions += 1

    # ---- 3. Frequency violations (>3 calls/day to same number) ----------
    frequency_violations = db.execute(text("""
        SELECT l.phone, l.owner_id, COUNT(*) as contact_count,
               CONCAT(l.first_name, ' ', l.last_name) as lead_name,
               l.id as lead_id
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('Call', 'SMS')
          AND l.phone IS NOT NULL
        GROUP BY l.phone, l.owner_id, l.first_name, l.last_name, l.id
        HAVING COUNT(*) > 3
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """), {"org_id": organization_id}).fetchall()

    for row in frequency_violations:
        phone, lo_id, count, lead_name, lead_id = row[0], row[1], row[2], row[3], row[4]
        if lo_id:
            lo_violations.setdefault(lo_id, {}).setdefault("frequency", 0)
            lo_violations[lo_id]["frequency"] += 1

        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id AND alert_type = 'TCPA_FREQUENCY'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"org_id": organization_id, "pattern": f"%phone={phone}%"}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, lead_id, organization_id, alert_type, severity, title,
                     description, status, created_at)
                VALUES
                    (NULL, :lead_id, :org_id, 'TCPA_FREQUENCY', 'high',
                     :title, :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "lead_id": lead_id,
                "org_id": organization_id,
                "title": f"TCPA frequency: {count} contacts to {lead_name} in 24h",
                "desc": (
                    f"phone={phone} | {count} outbound contacts to {lead_name} in 24 hours "
                    f"(limit: 3). Excessive contact frequency increases TCPA exposure."
                ),
            })
            actions += 1

    # ---- 4. Consent verification for marketing messages -----------------
    marketing_without_consent = db.execute(text("""
        SELECT a.id, l.id as lead_id, l.owner_id,
               CONCAT(l.first_name, ' ', l.last_name) as lead_name
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type = 'SMS'
          AND l.phone IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM sms_consent sc
              WHERE sc.phone_number = l.phone AND sc.consent_given = true
          )
          AND NOT EXISTS (
              SELECT 1 FROM channel_preferences cp
              WHERE cp.lead_id = l.id AND cp.organization_id = :org_id
                AND cp.sms_consent = true
          )
        LIMIT 30
    """), {"org_id": organization_id}).fetchall()

    for row in marketing_without_consent:
        aid, lead_id, lo_id, lead_name = row[0], row[1], row[2], row[3]
        if lo_id:
            lo_violations.setdefault(lo_id, {}).setdefault("no_consent", 0)
            lo_violations[lo_id]["no_consent"] += 1

    if marketing_without_consent:
        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, organization_id, alert_type, severity, title,
                 description, status, created_at)
            VALUES
                (NULL, :org_id, 'TCPA_NO_CONSENT', 'high',
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "org_id": organization_id,
            "title": f"TCPA: {len(marketing_without_consent)} SMS without express consent",
            "desc": (
                f"{len(marketing_without_consent)} outbound SMS sent to contacts without "
                f"verified express written consent (checked sms_consent + channel_preferences). "
                f"TCPA requires prior express written consent for marketing messages."
            ),
        })
        actions += 1

    # ---- 5. Per-LO compliance score and report --------------------------
    lo_compliance_scores: Dict[int, float] = {}

    for lo_id in lo_violations:
        # Calculate compliant vs total contacts for this LO
        total = db.execute(text("""
            SELECT COUNT(*) FROM activities a
            JOIN leads l ON l.id = a.lead_id
            WHERE a.organization_id = :org_id AND l.owner_id = :lo_id
              AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
              AND a.type IN ('Call', 'SMS')
        """), {"org_id": organization_id, "lo_id": str(lo_id)}).scalar() or 0

        violation_count = sum(lo_violations[lo_id].values())
        compliant = max(0, total - violation_count)
        score = round((compliant / total * 100), 1) if total > 0 else 100.0
        lo_compliance_scores[lo_id] = score

        lo_name_row = db.execute(text("""
            SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :id
        """), {"id": str(lo_id)}).fetchone()
        lo_name = lo_name_row[0] if lo_name_row else f"User {lo_id}"

        # Create per-LO compliance report alert
        violation_breakdown = ", ".join(f"{k}: {v}" for k, v in lo_violations[lo_id].items())
        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, organization_id, alert_type, severity, title,
                 description, status, created_at)
            VALUES
                (NULL, :org_id, 'TCPA_LO_REPORT', :severity,
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "org_id": organization_id,
            "severity": "critical" if score < 80 else ("high" if score < 90 else "medium"),
            "title": f"TCPA compliance: {lo_name} — {score}%",
            "desc": (
                f"LO: {lo_name} (user_id={lo_id}) | Compliance score: {score}% | "
                f"Total contacts: {total} | Violations: {violation_count} "
                f"({violation_breakdown})"
            ),
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"TCPA compliance scanner commit failed: {e}")

    return {
        "summary": (
            f"{actions} TCPA alerts created — "
            f"{len(after_hours_violations)} quiet-hour, "
            f"{len(all_dnc_violations)} DNC, "
            f"{len(frequency_violations)} frequency, "
            f"{len(marketing_without_consent)} no-consent"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "quiet_hours_violations": len(after_hours_violations),
        "dnc_violations": len(all_dnc_violations),
        "frequency_violations": len(frequency_violations),
        "no_consent_violations": len(marketing_without_consent),
        "lo_compliance_scores": lo_compliance_scores,
    }


# ---------------------------------------------------------------------------
# 4. HMDA Data Collector
# ---------------------------------------------------------------------------

# Stage priority for HMDA: higher number = closer to closing = more urgent
_STAGE_PRIORITY = {
    "CLEAR_TO_CLOSE": 10, "CTC": 10, "CLOSING": 9, "DOCS": 8, "DOCS_OUT": 8,
    "APPROVED": 7, "CONDITIONAL_APPROVAL": 6, "UW_RECEIVED": 5,
    "UNDERWRITING": 5, "SUBMITTED": 4, "PROCESSING": 3, "DISCLOSED": 2,
}

_HMDA_REQUIRED_FIELDS = [
    ("loan_purpose", "Loan Purpose (purchase, refinance, etc.)"),
    ("property_type", "Property Type (single-family, condo, etc.)"),
    ("property_address", "Property Address"),
    ("amount", "Loan Amount"),
    ("loan_type", "Loan Type (conventional, FHA, VA, USDA)"),
    ("rate", "Interest Rate"),
    ("application_date", "Application Date"),
]

# Optional HMDA field — only check if column exists
_HMDA_OPTIONAL_FIELDS = [
    ("property_state", "Property State"),
    ("property_county", "Property County (for census tract)"),
]


@autonomous_agent(
    name="hmda_data_collector",
    description="Ensure HMDA-reportable data fields are complete on all loans",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=90,
)
def hmda_data_collector(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Check all HMDA-required fields on active loans, calculate completeness
    percentages, group by LO, and create batch remediation tasks."""
    actions = 0

    # ---- Fetch all active non-terminal loans ----------------------------
    active_loans = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.stage,
               l.loan_purpose, l.property_type, l.property_address, l.amount,
               l.loan_type, l.rate, l.application_date,
               l.property_state, l.property_county
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN (""" + TERMINAL_STAGES + """)
        ORDER BY l.stage, l.closing_date ASC NULLS LAST
        LIMIT 200
    """), {"org_id": organization_id}).fetchall()

    if not active_loans:
        return {
            "summary": "No active loans to check",
            "actions_taken": 0,
            "notifications_sent": 0,
            "org_readiness_pct": 100.0,
        }

    # ---- Analyze each loan's HMDA completeness --------------------------
    # Loan column indices from the query above
    COL_MAP = {
        "loan_purpose": 5, "property_type": 6, "property_address": 7,
        "amount": 8, "loan_type": 9, "rate": 10, "application_date": 11,
        "property_state": 12, "property_county": 13,
    }

    # per-LO aggregation: lo_id -> [{loan_info}]
    lo_incomplete_loans: Dict[int, List[Dict[str, Any]]] = {}
    total_fields = 0
    total_present = 0
    loans_complete = 0

    for loan in active_loans:
        loan_id = loan[0]
        loan_number = loan[1]
        borrower_name = loan[2]
        lo_id = loan[3]
        stage = loan[4] or ""

        missing_fields: List[str] = []
        loan_total = 0
        loan_present = 0

        # Check required fields
        for col_name, label in _HMDA_REQUIRED_FIELDS:
            idx = COL_MAP[col_name]
            val = loan[idx]
            loan_total += 1
            if val is None or (isinstance(val, (int, float)) and val == 0):
                missing_fields.append(label)
            else:
                loan_present += 1

        # Check optional fields (count toward completeness but not as missing)
        for col_name, label in _HMDA_OPTIONAL_FIELDS:
            idx = COL_MAP.get(col_name)
            if idx is not None:
                val = loan[idx]
                loan_total += 1
                if val is not None and str(val).strip():
                    loan_present += 1
                else:
                    missing_fields.append(label)

        total_fields += loan_total
        total_present += loan_present
        completeness_pct = round((loan_present / loan_total * 100), 1) if loan_total > 0 else 0

        if missing_fields:
            priority_score = _STAGE_PRIORITY.get(str(stage).upper(), 1)
            if lo_id:
                lo_incomplete_loans.setdefault(lo_id, []).append({
                    "loan_id": loan_id,
                    "loan_number": loan_number,
                    "borrower_name": borrower_name,
                    "stage": stage,
                    "completeness_pct": completeness_pct,
                    "missing_fields": missing_fields,
                    "priority_score": priority_score,
                })
        else:
            loans_complete += 1

    # ---- Create per-LO batch remediation tasks --------------------------
    for lo_id, incomplete_loans in lo_incomplete_loans.items():
        # Sort by priority (closest to closing first)
        incomplete_loans.sort(key=lambda x: -x["priority_score"])

        lo_name_row = db.execute(text("""
            SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :id
        """), {"id": str(lo_id)}).fetchone()
        lo_name = lo_name_row[0] if lo_name_row else f"User {lo_id}"

        # Check if a batch HMDA task already exists for this LO in last 7 days
        existing_task = db.execute(text("""
            SELECT id FROM tasks
            WHERE organization_id = :org_id AND owner_id = :lo_id
              AND title LIKE '%HMDA%batch%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 1
        """), {"org_id": organization_id, "lo_id": str(lo_id)}).fetchone()

        if existing_task:
            continue

        # Build loan detail list for task description
        loan_lines: List[str] = []
        for idx, loan_info in enumerate(incomplete_loans[:15], 1):
            fields_str = ", ".join(loan_info["missing_fields"])
            loan_lines.append(
                f"  {idx}. {loan_info['borrower_name']} ({loan_info['loan_number']}) "
                f"[{loan_info['stage']}] — {loan_info['completeness_pct']}% complete. "
                f"Missing: {fields_str}"
            )

        more_note = ""
        if len(incomplete_loans) > 15:
            more_note = f"\n  ... and {len(incomplete_loans) - 15} more loans."

        # Determine priority based on how close loans are to closing
        max_priority = max(l["priority_score"] for l in incomplete_loans)
        task_priority = "high" if max_priority >= 7 else ("medium" if max_priority >= 4 else "low")

        db.execute(text("""
            INSERT INTO tasks
                (title, description, owner_id, priority, status,
                 due_date, created_at, organization_id)
            VALUES
                (:title, :desc, :lo_id, :priority, 'pending',
                 CURRENT_DATE + 5, CURRENT_TIMESTAMP, :org_id)
        """), {
            "title": f"HMDA data batch: {len(incomplete_loans)} loans need data — {lo_name}",
            "desc": (
                f"HMDA data completeness audit found {len(incomplete_loans)} loans "
                f"with missing required fields:\n\n"
                + "\n".join(loan_lines)
                + more_note
                + "\n\nHMDA (Home Mortgage Disclosure Act) requires these fields for "
                f"regulatory reporting. Prioritized by proximity to closing."
            ),
            "lo_id": str(lo_id),
            "priority": task_priority,
            "org_id": organization_id,
        })
        actions += 1

    # ---- Create org-wide compliance alert with completeness summary ------
    org_readiness = round((total_present / total_fields * 100), 1) if total_fields > 0 else 100.0

    if org_readiness < 95:
        severity = "high" if org_readiness < 80 else "medium"
        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, organization_id, alert_type, severity, title,
                 description, status, created_at)
            VALUES
                (NULL, :org_id, 'HMDA_READINESS', :severity,
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "org_id": organization_id,
            "severity": severity,
            "title": f"HMDA readiness: {org_readiness}% org-wide",
            "desc": (
                f"Org HMDA data readiness: {org_readiness}%. "
                f"{loans_complete}/{len(active_loans)} loans fully complete. "
                f"{len(active_loans) - loans_complete} loans need attention across "
                f"{len(lo_incomplete_loans)} LOs."
            ),
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"HMDA data collector commit failed: {e}")

    return {
        "summary": (
            f"{actions} actions — {loans_complete}/{len(active_loans)} loans HMDA-complete, "
            f"org readiness {org_readiness}%"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "org_readiness_pct": org_readiness,
        "total_loans_checked": len(active_loans),
        "loans_complete": loans_complete,
        "loans_incomplete": len(active_loans) - loans_complete,
        "los_with_incomplete": len(lo_incomplete_loans),
    }


# ---------------------------------------------------------------------------
# 5. Fair Lending Monitor
# ---------------------------------------------------------------------------

def _z_score(value: float, mean: float, std: float) -> float:
    """Calculate z-score. Returns 0 if std is 0."""
    if std == 0 or std is None:
        return 0.0
    return (value - mean) / std


def _std_dev(values: List[float]) -> float:
    """Standard deviation of a list of floats."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


@autonomous_agent(
    name="fair_lending_monitor",
    description="Statistical analysis of lending patterns for fair lending compliance",
    frequency=AgentFrequency.WEEKLY_MONDAY,
    max_runtime_seconds=120,
)
def fair_lending_monitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Analyze approval/denial rates by loan type, pricing distribution across
    LOs, turnaround time variance, and steering indicators with statistical
    significance testing."""
    actions = 0
    findings: List[Dict[str, Any]] = []

    # ---- 1. Denial rates segmented by loan type -------------------------
    denial_by_type = db.execute(text("""
        SELECT l.loan_type,
               l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               COUNT(*) as total,
               COUNT(CASE WHEN l.stage IN ('DENIED','DOES_NOT_QUALIFY') THEN 1 END) as denied,
               ROUND(
                   COUNT(CASE WHEN l.stage IN ('DENIED','DOES_NOT_QUALIFY') THEN 1 END)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 2
               ) as denial_rate
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.created_at >= CURRENT_DATE - 90
          AND l.loan_type IS NOT NULL
        GROUP BY l.loan_type, l.loan_officer_id, u.first_name, u.last_name
        HAVING COUNT(*) >= 3
        ORDER BY l.loan_type, denial_rate DESC
    """), {"org_id": organization_id}).fetchall()

    # Group by loan type for cross-LO comparison
    type_groups: Dict[str, List[Tuple]] = {}
    for row in denial_by_type:
        loan_type = str(row[0] or "Unknown")
        type_groups.setdefault(loan_type, []).append(row)

    for loan_type, rows in type_groups.items():
        if len(rows) < 2:
            continue

        rates = [float(r[5] or 0) for r in rows]
        mean_rate = sum(rates) / len(rates)
        std = _std_dev(rates)

        for row in rows:
            rate = float(row[5] or 0)
            z = _z_score(rate, mean_rate, std)
            lo_name = row[2]
            total = row[3]
            denied = row[4]

            # Flag if z-score > 1.96 (95% confidence) and practical significance
            if z > 1.96 and rate > mean_rate + 10 and rate > 15:
                findings.append({
                    "type": "high_denial_rate",
                    "loan_type": loan_type,
                    "lo_name": lo_name,
                    "lo_id": row[1],
                    "rate": rate,
                    "mean": mean_rate,
                    "z_score": round(z, 2),
                    "total": total,
                    "denied": denied,
                })

                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :org_id, 'FAIR_LENDING_DENIAL', :severity,
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "severity": "high" if z > 2.5 else "medium",
                    "title": f"Fair lending: {lo_name} — {rate}% denial rate on {loan_type}",
                    "desc": (
                        f"LO: {lo_name} | Loan type: {loan_type} | Denial rate: {rate}% "
                        f"({denied}/{total}) vs org avg {mean_rate:.1f}% | "
                        f"Z-score: {z:.2f} (statistically significant at 95%)\n\n"
                        f"Remediation: Review denied applications for this LO on {loan_type} "
                        f"loans. Verify denial reasons are consistently applied and documented. "
                        f"Compare underwriting criteria across loan officers."
                    ),
                })
                actions += 1

    # ---- 2. Pricing (rate) distribution analysis across LOs -------------
    pricing_by_lo = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               l.loan_type,
               AVG(l.rate) as avg_rate,
               COUNT(*) as loan_count,
               MIN(l.rate) as min_rate,
               MAX(l.rate) as max_rate
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.created_at >= CURRENT_DATE - 90
          AND l.rate IS NOT NULL AND l.rate > 0
          AND l.loan_type IS NOT NULL
          AND l.stage NOT IN ('CANCELLED','DEAD','WITHDRAWN')
        GROUP BY l.loan_officer_id, u.first_name, u.last_name, l.loan_type
        HAVING COUNT(*) >= 3
        ORDER BY l.loan_type
    """), {"org_id": organization_id}).fetchall()

    # Group by loan type for cross-LO comparison
    pricing_groups: Dict[str, List[Tuple]] = {}
    for row in pricing_by_lo:
        lt = str(row[2] or "Unknown")
        pricing_groups.setdefault(lt, []).append(row)

    for loan_type, rows in pricing_groups.items():
        if len(rows) < 2:
            continue

        avg_rates = [float(r[3] or 0) for r in rows]
        mean_rate = sum(avg_rates) / len(avg_rates)
        std = _std_dev(avg_rates)

        for row in rows:
            avg_rate = float(row[3] or 0)
            z = _z_score(avg_rate, mean_rate, std)
            lo_name = row[1]

            # Flag outlier pricing (significantly higher rates)
            if z > 1.96 and avg_rate > mean_rate + 0.25:
                findings.append({
                    "type": "pricing_outlier",
                    "loan_type": loan_type,
                    "lo_name": lo_name,
                    "lo_id": row[0],
                    "avg_rate": round(avg_rate, 4),
                    "org_mean": round(mean_rate, 4),
                    "z_score": round(z, 2),
                })

                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :org_id, 'FAIR_LENDING_PRICING', :severity,
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "severity": "high" if z > 2.5 else "medium",
                    "title": f"Fair lending: Pricing outlier — {lo_name} on {loan_type}",
                    "desc": (
                        f"LO: {lo_name} | Loan type: {loan_type} | Avg rate: {avg_rate:.3f}% "
                        f"vs org avg {mean_rate:.3f}% | Z-score: {z:.2f}\n"
                        f"Rate range: {float(row[5]):.3f}% - {float(row[6]):.3f}% across "
                        f"{row[4]} loans.\n\n"
                        f"Remediation: Audit rate sheets used. Verify pricing exceptions are "
                        f"documented with valid business justification. Compare discount point "
                        f"and fee structures."
                    ),
                })
                actions += 1

    # ---- 3. Turnaround time variance analysis ----------------------------
    turnaround_by_lo = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               l.loan_type,
               AVG(EXTRACT(DAY FROM (l.stage_changed_at - l.application_date))) as avg_days,
               COUNT(*) as funded_count,
               MIN(EXTRACT(DAY FROM (l.stage_changed_at - l.application_date))) as min_days,
               MAX(EXTRACT(DAY FROM (l.stage_changed_at - l.application_date))) as max_days
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.application_date IS NOT NULL
          AND l.stage_changed_at IS NOT NULL
          AND l.stage_changed_at >= CURRENT_DATE - 90
          AND l.loan_type IS NOT NULL
        GROUP BY l.loan_officer_id, u.first_name, u.last_name, l.loan_type
        HAVING COUNT(*) >= 2
    """), {"org_id": organization_id}).fetchall()

    # Group by loan type
    time_groups: Dict[str, List[Tuple]] = {}
    for row in turnaround_by_lo:
        lt = str(row[2] or "Unknown")
        time_groups.setdefault(lt, []).append(row)

    for loan_type, rows in time_groups.items():
        if len(rows) < 2:
            continue

        avg_days_list = [float(r[3] or 0) for r in rows]
        mean_days = sum(avg_days_list) / len(avg_days_list)
        std = _std_dev(avg_days_list)

        for row in rows:
            days = float(row[3] or 0)
            z = _z_score(days, mean_days, std)
            lo_name = row[1]

            if z > 1.96 and days > mean_days + 10 and days > 35:
                findings.append({
                    "type": "slow_processing",
                    "loan_type": loan_type,
                    "lo_name": lo_name,
                    "lo_id": row[0],
                    "avg_days": round(days, 1),
                    "org_mean": round(mean_days, 1),
                    "z_score": round(z, 2),
                })

                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :org_id, 'FAIR_LENDING_TIMING', :severity,
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "severity": "high" if z > 2.5 else "medium",
                    "title": f"Fair lending: Slow processing — {lo_name} on {loan_type}",
                    "desc": (
                        f"LO: {lo_name} | Loan type: {loan_type} | Avg {days:.0f} days to fund "
                        f"vs org avg {mean_days:.0f} | Z-score: {z:.2f}\n"
                        f"Range: {float(row[5]):.0f}-{float(row[6]):.0f} days across "
                        f"{row[4]} funded loans.\n\n"
                        f"Remediation: Review processing bottlenecks for this LO's {loan_type} "
                        f"loans. May indicate disparate treatment if certain loan types or "
                        f"borrower profiles consistently experience delays."
                    ),
                })
                actions += 1

    # ---- 4. Steering analysis: LO loan-type distribution ----------------
    lo_type_distribution = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               l.loan_type,
               COUNT(*) as type_count
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.created_at >= CURRENT_DATE - 90
          AND l.loan_type IS NOT NULL
          AND l.stage NOT IN ('CANCELLED','DEAD','WITHDRAWN')
        GROUP BY l.loan_officer_id, u.first_name, u.last_name, l.loan_type
        ORDER BY l.loan_officer_id, type_count DESC
    """), {"org_id": organization_id}).fetchall()

    # Calculate org-wide loan-type distribution
    org_type_counts: Dict[str, int] = {}
    org_total = 0
    lo_type_map: Dict[int, Dict[str, int]] = {}  # lo_id -> {type: count}

    for row in lo_type_distribution:
        lo_id, lo_name, loan_type, count = row[0], row[1], str(row[2]), int(row[3])
        org_type_counts[loan_type] = org_type_counts.get(loan_type, 0) + count
        org_total += count
        lo_type_map.setdefault(lo_id, {})[loan_type] = count

    if org_total > 0:
        org_type_pct = {lt: (cnt / org_total * 100) for lt, cnt in org_type_counts.items()}

        for lo_id, type_counts in lo_type_map.items():
            lo_total = sum(type_counts.values())
            if lo_total < 5:
                continue

            for loan_type, count in type_counts.items():
                lo_pct = (count / lo_total) * 100
                org_pct = org_type_pct.get(loan_type, 0)

                # Flag if LO's distribution for a type is 2x+ the org average
                # and the loan type has fair-lending implications (FHA/VA)
                if (lo_pct > org_pct * 2 and lo_pct > 30 and
                        loan_type.upper() in ("FHA", "VA", "USDA")):
                    lo_name_row = db.execute(text("""
                        SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :id
                    """), {"id": str(lo_id)}).fetchone()
                    lo_name = lo_name_row[0] if lo_name_row else f"User {lo_id}"

                    findings.append({
                        "type": "steering_indicator",
                        "lo_name": lo_name,
                        "lo_id": lo_id,
                        "loan_type": loan_type,
                        "lo_pct": round(lo_pct, 1),
                        "org_pct": round(org_pct, 1),
                    })

                    db.execute(text("""
                        INSERT INTO compliance_alerts
                            (loan_id, organization_id, alert_type, severity, title,
                             description, status, created_at)
                        VALUES
                            (NULL, :org_id, 'FAIR_LENDING_STEERING', 'medium',
                             :title, :desc, 'open', CURRENT_TIMESTAMP)
                    """), {
                        "org_id": organization_id,
                        "title": f"Fair lending: Potential steering — {lo_name} → {loan_type}",
                        "desc": (
                            f"LO: {lo_name} | {lo_pct:.1f}% of loans are {loan_type} vs "
                            f"org avg {org_pct:.1f}% ({count}/{lo_total} loans).\n\n"
                            f"Steering occurs when borrowers who qualify for conventional "
                            f"financing are directed toward government-backed programs. "
                            f"Review whether {loan_type} borrowers were presented all options.\n\n"
                            f"Remediation: Audit loan program selection documentation. Verify "
                            f"borrowers received comparison of all eligible products. Review "
                            f"qualification criteria applied."
                        ),
                    })
                    actions += 1

    # ---- 5. Generate summary activity log entry -------------------------
    finding_summary_lines = []
    for f in findings[:20]:
        if f["type"] == "high_denial_rate":
            finding_summary_lines.append(
                f"  - {f['lo_name']}: {f['rate']}% denial on {f['loan_type']} "
                f"(z={f['z_score']}, org avg {f['mean']:.1f}%)"
            )
        elif f["type"] == "pricing_outlier":
            finding_summary_lines.append(
                f"  - {f['lo_name']}: {f['avg_rate']}% avg rate on {f['loan_type']} "
                f"(z={f['z_score']}, org avg {f['org_mean']:.3f}%)"
            )
        elif f["type"] == "slow_processing":
            finding_summary_lines.append(
                f"  - {f['lo_name']}: {f['avg_days']} days avg on {f['loan_type']} "
                f"(z={f['z_score']}, org avg {f['org_mean']:.0f})"
            )
        elif f["type"] == "steering_indicator":
            finding_summary_lines.append(
                f"  - {f['lo_name']}: {f['lo_pct']}% {f['loan_type']} vs "
                f"org avg {f['org_pct']}%"
            )

    report_content = (
        f"[FAIR LENDING MONITOR] Weekly analysis — {len(findings)} findings.\n"
        f"Checks: denial rates by type, pricing distribution, turnaround time, "
        f"steering indicators.\n"
    )
    if finding_summary_lines:
        report_content += "Findings:\n" + "\n".join(finding_summary_lines)
    else:
        report_content += "No statistically significant disparities detected."

    db.execute(text("""
        INSERT INTO activities (lead_id, loan_id, type, content, created_at, organization_id)
        VALUES (NULL, NULL, 'Note', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": report_content[:2000], "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Fair lending monitor commit failed: {e}")

    return {
        "summary": f"{actions} fair lending alerts, {len(findings)} statistical findings",
        "actions_taken": actions,
        "notifications_sent": 0,
        "findings_count": len(findings),
        "findings_by_type": {
            "denial_rate": sum(1 for f in findings if f["type"] == "high_denial_rate"),
            "pricing_outlier": sum(1 for f in findings if f["type"] == "pricing_outlier"),
            "slow_processing": sum(1 for f in findings if f["type"] == "slow_processing"),
            "steering": sum(1 for f in findings if f["type"] == "steering_indicator"),
        },
        "loan_types_analyzed": list(type_groups.keys()) if type_groups else [],
    }
