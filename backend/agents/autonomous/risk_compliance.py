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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency
from agents.autonomous.memory_context import get_lo_memory_context, get_org_directives

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_TERMINAL_SQL = (
    "('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')"
)

# US state -> IANA timezone (TCPA quiet-hours enforcement)
_STATE_TIMEZONE: Dict[str, str] = {
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
    offsets: Dict[str, int] = {
        "America/New_York": -5, "America/Chicago": -6, "America/Denver": -7,
        "America/Los_Angeles": -8, "America/Anchorage": -9, "Pacific/Honolulu": -10,
        "America/Phoenix": -7, "America/Boise": -7, "America/Detroit": -5,
        "America/Indiana/Indianapolis": -5,
    }
    return offsets.get(tz_name, -5)


def _extract_state_from_address(address: str) -> Optional[str]:
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


def _safe_str(val: Any, max_len: int = 300) -> str:
    """Safely coerce a value to a truncated string."""
    if val is None:
        return ""
    s = str(val)
    return s[:max_len] if len(s) > max_len else s


# ---------------------------------------------------------------------------
# Domain similarity detection (typosquatting / spoofing)
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance between two strings."""
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
    return prev[la]


def _domains_similar(candidate: str, verified: str) -> bool:
    """Detect typosquatting: domains that are close but not identical.

    Checks Levenshtein distance <= 2 AND length difference <= 3.
    Also catches common spoofing tricks: rn->m, l->1, 0->o, vv->w.
    """
    if not candidate or not verified:
        return False
    if candidate == verified:
        return False  # Exact match is not spoofing
    if abs(len(candidate) - len(verified)) > 3:
        return False

    # Normalize common spoofing substitutions before distance check
    def _normalize(d: str) -> str:
        return d.replace("rn", "m").replace("vv", "w").replace("1", "l").replace("0", "o")

    if _normalize(candidate) == _normalize(verified):
        return True  # Homoglyph match

    dist = _levenshtein(candidate, verified)
    return 0 < dist <= 2


# ============================================================================
# 1. Wire Fraud Scanner
# ============================================================================

@autonomous_agent(
    name="wire_fraud_scanner",
    description="Scan for suspicious wire/email patterns indicating fraud attempts",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def wire_fraud_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Detect emails with wire instruction changes, domain spoofing, and
    urgency-language patterns that indicate potential wire fraud.

    Scans activities from the last 15 minutes for three categories of risk:
    - Wire instruction changes (routing/account number modifications)
    - Urgency language combined with financial keywords
    - After-hours emails referencing wire/closing/funds

    Creates CRITICAL compliance alerts with recommended actions and logs
    an audit-trail activity on the affected lead/loan record.
    """
    actions = 0
    false_positives_suppressed = 0
    fraud_indicators_found: List[Dict[str, Any]] = []

    # -- Collect verified domains from active loan records ------------------
    # Uses title_company and lender fields plus borrower/LO email domains
    # to build a whitelist for domain-spoof detection.
    verified_domains: set = set()
    try:
        verified_rows = db.execute(text("""
            SELECT DISTINCT LOWER(TRIM(SPLIT_PART(l.borrower_email, '@', 2))) AS domain
            FROM loans l
            WHERE l.organization_id = :org_id
              AND l.borrower_email IS NOT NULL
              AND l.stage NOT IN """ + _TERMINAL_SQL + """
            UNION
            SELECT DISTINCT LOWER(TRIM(SPLIT_PART(l.loan_officer_email, '@', 2))) AS domain
            FROM loans l
            WHERE l.organization_id = :org_id
              AND l.loan_officer_email IS NOT NULL
              AND l.stage NOT IN """ + _TERMINAL_SQL + """
        """), {"org_id": organization_id}).fetchall()
        verified_domains = {row[0] for row in verified_rows if row[0]}
    except Exception as e:
        logger.warning(f"Wire fraud scanner: could not load verified domains: {e}")

    # -- Scan 1: Wire instruction change keywords --------------------------
    wire_change_rows = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) AS responsible_user_id,
               COALESCE(ln.borrower_name, CONCAT(l.first_name, ' ', l.last_name)) AS contact_name
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        LEFT JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
          AND a.type IN ('Email', 'System', 'Note')
          AND (
              LOWER(a.content) LIKE '%wire%instruct%'
              OR LOWER(a.content) LIKE '%routing%number%changed%'
              OR LOWER(a.content) LIKE '%new%routing%number%'
              OR LOWER(a.content) LIKE '%new%bank%account%'
              OR LOWER(a.content) LIKE '%updated%closing%account%'
              OR LOWER(a.content) LIKE '%send%funds%to%'
              OR LOWER(a.content) LIKE '%wiring%details%changed%'
              OR LOWER(a.content) LIKE '%account%number%updated%'
              OR LOWER(a.content) LIKE '%transfer%immediately%'
          )
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    # -- Scan 2: Urgency language in emails --------------------------------
    urgency_rows = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) AS responsible_user_id,
               COALESCE(ln.borrower_name, CONCAT(l.first_name, ' ', l.last_name)) AS contact_name
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
              OR LOWER(a.content) LIKE '%immediately%transfer%'
          )
        LIMIT 30
    """), {"org_id": organization_id}).fetchall()

    # -- Scan 3: After-hours emails referencing wire/closing/funds ---------
    after_hours_rows = db.execute(text("""
        SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
               COALESCE(l.owner_id, ln.loan_officer_id) AS responsible_user_id,
               COALESCE(ln.borrower_name, CONCAT(l.first_name, ' ', l.last_name)) AS contact_name
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        LEFT JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
          AND a.type = 'Email'
          AND (EXTRACT(HOUR FROM a.created_at AT TIME ZONE :tz) < 7
               OR EXTRACT(HOUR FROM a.created_at AT TIME ZONE :tz) >= 20)
          AND (
              LOWER(a.content) LIKE '%wire%'
              OR LOWER(a.content) LIKE '%closing%'
              OR LOWER(a.content) LIKE '%funds%'
          )
        LIMIT 20
    """), {"org_id": organization_id, "tz": org_timezone}).fetchall()

    # -- Deduplicate and merge all suspicious activities --------------------
    seen_ids: set = set()
    all_suspicious: List[Tuple] = []
    indicator_labels: Dict[int, List[str]] = {}

    for row in wire_change_rows:
        aid = row[0]
        if aid not in seen_ids:
            seen_ids.add(aid)
            all_suspicious.append(row)
        indicator_labels.setdefault(aid, []).append("WIRE_INSTRUCTION_CHANGE")

    for row in urgency_rows:
        aid = row[0]
        if aid not in seen_ids:
            seen_ids.add(aid)
            all_suspicious.append(row)
        indicator_labels.setdefault(aid, []).append("URGENCY_LANGUAGE")

    for row in after_hours_rows:
        aid = row[0]
        if aid not in seen_ids:
            seen_ids.add(aid)
            all_suspicious.append(row)
        indicator_labels.setdefault(aid, []).append("AFTER_HOURS_URGENCY")

    # -- Domain spoofing check on email content ----------------------------
    for row in all_suspicious:
        content_lower = _safe_str(row[3], 5000).lower()
        # Extract sender domain from "From: user@domain.com" pattern
        domain_match = re.search(r'from[:\s]+\S+@([\w.-]+)', content_lower)
        if domain_match and verified_domains:
            sender_domain = domain_match.group(1)
            for vd in verified_domains:
                if not vd:
                    continue
                if _domains_similar(sender_domain, vd):
                    indicator_labels.setdefault(row[0], []).append(
                        f"DOMAIN_SPOOF ('{sender_domain}' mimics '{vd}')"
                    )
                    break

    # -- Create compliance alerts for each suspicious activity -------------
    for row in all_suspicious:
        activity_id = row[0]
        lead_id = row[1]
        loan_id = row[2]
        content_snippet = _safe_str(row[3], 300)
        contact_name = _safe_str(row[6]) or "Unknown"
        indicators = indicator_labels.get(activity_id, ["SUSPICIOUS_CONTENT"])

        # Dedup: skip if alert already exists for this activity in last 24h
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id
              AND alert_type = 'WIRE_FRAUD_SUSPECT'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {
            "org_id": organization_id,
            "pattern": f"%activity_id={activity_id}%",
        }).fetchone()

        if existing:
            false_positives_suppressed += 1
            continue

        # Severity: CRITICAL for wire instruction changes or domain spoofing;
        # HIGH for urgency language or after-hours patterns alone.
        severity = "critical" if (
            "WIRE_INSTRUCTION_CHANGE" in indicators
            or any("DOMAIN_SPOOF" in i for i in indicators)
        ) else "high"

        indicator_str = ", ".join(indicators)
        description = (
            f"WIRE FRAUD ALERT | activity_id={activity_id} | Contact: {contact_name}\n"
            f"Fraud indicators: {indicator_str}\n"
            f"Content snippet: {content_snippet}\n\n"
            f"RECOMMENDED ACTION: Do NOT wire funds. Call the title company at their "
            f"verified phone number (from your original engagement letter or HUD-1). "
            f"Never rely on contact information provided in a suspicious email. "
            f"If wire instructions have changed, treat as presumptive fraud until "
            f"confirmed verbally with a known contact."
        )

        _wf_title = f"Wire fraud alert: {indicator_str} -- {contact_name}"[:200]
        _wf_desc = description[:2000]
        def _do_wf_alert(t=_wf_title, d=_wf_desc, lid=loan_id, leid=lead_id, sev=severity):
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, lead_id, organization_id, alert_type, severity, title,
                     description, status, created_at)
                VALUES
                    (:loan_id, :lead_id, :org_id, 'WIRE_FRAUD_SUSPECT', :severity,
                     :title, :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "loan_id": lid,
                "lead_id": leid,
                "org_id": organization_id,
                "severity": sev,
                "title": t,
                "desc": d,
            })
        if gateway:
            gateway.propose("create_compliance_alert", _do_wf_alert, target_entity="loan", target_id=str(loan_id), description=_wf_title[:200],
                payload={"loan_id": loan_id, "lead_id": lead_id, "org_id": organization_id, "severity": severity, "title": _wf_title, "desc": _wf_desc})
        else:
            _do_wf_alert()

        # Audit trail: log activity on the lead/loan record
        _wf_activity_content = (
            f"[WIRE FRAUD SCANNER] Alert created -- indicators: {indicator_str}. "
            f"Do NOT wire funds without verbal verification at a verified number."
        )[:2000]
        def _do_wf_activity(c=_wf_activity_content, lid=loan_id, leid=lead_id):
            db.execute(text("""
                INSERT INTO activities
                    (lead_id, loan_id, type, content, created_at, organization_id)
                VALUES
                    (:lead_id, :loan_id, 'Note', :content, CURRENT_TIMESTAMP, :org_id)
            """), {
                "lead_id": leid,
                "loan_id": lid,
                "content": c,
                "org_id": organization_id,
            })
        if gateway:
            gateway.propose("create_activity", _do_wf_activity, target_entity="loan", target_id=str(loan_id), description=_wf_activity_content[:200],
                payload={"lead_id": lead_id, "loan_id": loan_id, "content": _wf_activity_content, "org_id": organization_id})
        else:
            _do_wf_activity()

        fraud_indicators_found.append({
            "activity_id": activity_id,
            "indicators": indicators,
            "severity": severity,
            "contact_name": contact_name,
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Wire fraud scanner commit failed for org {organization_id}: {e}")

    return {
        "summary": (
            f"{actions} wire fraud alert(s) created, "
            f"{false_positives_suppressed} deduped, "
            f"{len(all_suspicious)} suspicious activities scanned"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "fraud_indicators": fraud_indicators_found,
        "false_positives_suppressed": false_positives_suppressed,
        "activities_scanned": len(all_suspicious),
        "verified_domains_count": len(verified_domains),
    }


# ============================================================================
# 2. ECOA Audit Agent
# ============================================================================

# Prohibited patterns organized by ECOA category.
# Each category maps to regex patterns and a default severity.
# Direct questions about protected characteristics = critical.
# Indirect or ambiguous references = high or medium.
_ECOA_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "race_ethnicity": {
        "label": "Race / Ethnicity",
        "patterns": [
            r"\brace\b", r"\bethnicit", r"\bethnic\b", r"\bhispanic\b",
            r"\blatino\b", r"\bcaucasian\b", r"\bafrican.?american\b",
            r"\basian\b(?!.*pacific.*mortgage)", r"\bwhite\b(?!.*pages|.*paper)",
            r"\bblack\b(?!.*list|.*out|.*stone)",
        ],
        "direct_severity": "critical",
        "indirect_severity": "high",
        "training": "ECOA Fair Lending Training Module 1: Race & Ethnicity",
    },
    "sex_gender": {
        "label": "Sex / Gender",
        "patterns": [
            r"what.{0,10}gender", r"are you (?:male|female)", r"\bsex\b(?!.*offend)",
            r"\bpregnant\b", r"\bpregnancy\b",
        ],
        "direct_severity": "critical",
        "indirect_severity": "high",
        "training": "ECOA Fair Lending Training Module 2: Gender & Sex Discrimination",
    },
    "religion": {
        "label": "Religion",
        "patterns": [
            r"what.{0,10}religion", r"are you (?:christian|muslim|jewish|hindu|buddhist)",
            r"\breligious\b(?!.*holiday)", r"what church",
        ],
        "direct_severity": "critical",
        "indirect_severity": "high",
        "training": "ECOA Fair Lending Training Module 3: Religious Discrimination",
    },
    "national_origin": {
        "label": "National Origin",
        "patterns": [
            r"(?:where|what country).{0,15}(?:from|born|citizen)",
            r"\bnational origin\b", r"\bimmigr(?:ant|ation)\b(?!.*visa.*status)",
            r"are you.{0,10}american", r"\bcitizenship\b(?!.*status.*verified)",
        ],
        "direct_severity": "critical",
        "indirect_severity": "high",
        "training": "ECOA Fair Lending Training Module 4: National Origin",
    },
    "age": {
        "label": "Age",
        "patterns": [
            r"how old are you", r"what(?:'s| is) your age", r"\byour age\b",
            r"date of birth(?!.*verify|.*confirm|.*application)",
            r"when were you born(?!.*verify)",
        ],
        "direct_severity": "high",
        "indirect_severity": "medium",
        "training": "ECOA Fair Lending Training Module 5: Age Discrimination (Reg B)",
    },
    "marital_status": {
        "label": "Marital Status",
        "patterns": [
            r"are you married", r"marital status(?!.*on.*application)",
            r"are you (?:single|divorced|separated|widowed)",
            r"\bspouse\b(?!.*co.?borrower|.*income|.*on.*loan)",
        ],
        "direct_severity": "high",
        "indirect_severity": "medium",
        "training": "ECOA Fair Lending Training Module 6: Marital Status",
    },
    "familial_status": {
        "label": "Familial Status",
        "patterns": [
            r"(?:do you|how many).{0,10}(?:children|kids)",
            r"are you.{0,10}(?:expecting|pregnant)",
            r"\bfamilial status\b", r"planning.{0,10}family",
        ],
        "direct_severity": "high",
        "indirect_severity": "medium",
        "training": "Fair Housing Training Module: Familial Status",
    },
    "disability": {
        "label": "Disability",
        "patterns": [
            r"(?:do you|are you).{0,15}(?:disabled|handicap|disability)",
            r"\bphysical.{0,10}limitation\b", r"\bmental.{0,10}(?:illness|condition)\b",
        ],
        "direct_severity": "critical",
        "indirect_severity": "high",
        "training": "Fair Housing Training Module: Disability Accommodations",
    },
}

# Patterns that look like direct questions (LO asking the borrower)
_DIRECT_QUESTION_RE = re.compile(
    r'(?:what|are you|do you|how|tell me|your)\b', re.IGNORECASE
)


@autonomous_agent(
    name="ecoa_audit",
    description="Verify no prohibited questions (race, sex, religion) in AI conversations",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=120,
)
def ecoa_audit(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Scan AI conversations, call transcripts, and note activities for
    ECOA-prohibited topics (Regulation B, 12 CFR 1002).

    Categorizes violations by type, scores severity (direct question = critical,
    indirect = high, ambiguous = medium), checks for repeat offenders within
    90 days, and creates remediation tasks with specific training recommendations.
    """
    actions = 0
    violations_by_category: Dict[str, int] = {}
    repeat_offenders: Dict[int, int] = {}  # user_id -> violations today

    # -- Collect scannable text segments -----------------------------------
    # Each segment: (source_type, source_id, user_id, text, is_ai_response)
    text_segments: List[Tuple[str, int, Optional[int], str, bool]] = []

    # 1. AI chat conversations
    try:
        conversations = db.execute(text("""
            SELECT c.id, c.user_id, c.message, c.response, c.created_at
            FROM conversations c
            WHERE c.organization_id = :org_id
              AND c.created_at >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY c.created_at DESC
            LIMIT 500
        """), {"org_id": organization_id}).fetchall()

        for row in conversations:
            cid, user_id, message, response = row[0], row[1], row[2], row[3]
            if message:
                text_segments.append(("conversation", cid, user_id, str(message), False))
            if response:
                text_segments.append(("conversation", cid, user_id, str(response), True))
    except Exception as e:
        logger.debug(f"ECOA audit: conversations table not available: {e}")

    # 2. Agent conversation summaries
    try:
        agent_convos = db.execute(text("""
            SELECT ac.id, ac.user_id, ac.summary, ac.key_points, ac.started_at
            FROM agent_conversations ac
            WHERE ac.organization_id = :org_id
              AND ac.started_at >= CURRENT_DATE - INTERVAL '1 day'
              AND ac.summary IS NOT NULL
            ORDER BY ac.started_at DESC
            LIMIT 200
        """), {"org_id": organization_id}).fetchall()

        for row in agent_convos:
            acid, user_id, summary = row[0], row[1], row[2]
            if summary:
                text_segments.append(("agent_conversation", acid, user_id, str(summary), True))
            if row[3]:
                kp_str = str(row[3])
                if len(kp_str) > 10:
                    text_segments.append(("agent_conversation", acid, user_id, kp_str, True))
    except Exception as e:
        logger.debug(f"ECOA audit: agent_conversations table not available: {e}")

    # 3. Call transcripts and notes from activities
    try:
        call_activities = db.execute(text("""
            SELECT a.id, a.lead_id, a.loan_id, a.content, a.created_at,
                   COALESCE(l.owner_id, ln.loan_officer_id) AS user_id
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

        for row in call_activities:
            aid, lead_id, loan_id, content, _, user_id = row
            if content:
                text_segments.append(("activity", aid, user_id, str(content), False))
    except Exception as e:
        logger.debug(f"ECOA audit: activities scan failed: {e}")

    # -- Pattern matching across all text segments -------------------------
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

                    # Determine severity: direct question = critical/high,
                    # indirect mention = high/medium, AI response = escalate
                    is_direct = bool(_DIRECT_QUESTION_RE.search(content_lower))
                    if is_direct:
                        severity = cfg["direct_severity"]
                    else:
                        severity = cfg["indirect_severity"]

                    # AI responses producing prohibited content are always critical
                    if is_ai_response and severity != "critical":
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

    # -- Check 90-day repeat offender history ------------------------------
    repeat_offender_history: Dict[int, int] = {}
    for user_id in repeat_offenders:
        if not user_id:
            continue
        try:
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
                repeat_offender_history[user_id] = prior_count
        except Exception as e:
            logger.warning(f"ECOA audit: repeat offender check failed for user {user_id}: {e}")

    # -- Create alerts and remediation tasks -------------------------------
    for v in found_violations:
        # Dedup against existing alerts in last 24h
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id
              AND alert_type = 'ECOA_VIOLATION'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {
            "org_id": organization_id,
            "pattern": f"%{v['source_type']}={v['source_id']}%{v['category']}%",
        }).fetchone()

        if existing:
            continue

        prior_offenses = repeat_offender_history.get(v["user_id"], 0)
        repeat_note = ""
        if prior_offenses > 0:
            repeat_note = (
                f" REPEAT OFFENDER: {prior_offenses} prior ECOA alert(s) in 90 days. "
                f"Escalation recommended."
            )

        category_label = _ECOA_CATEGORIES[v["category"]]["label"]
        description = (
            f"ECOA violation detected | {v['source_type']}={v['source_id']} | "
            f"user_id={v['user_id']}\n"
            f"Category: {category_label}\n"
            f"Source: {v['source_label']}\n"
            f"Severity: {v['severity']}\n"
            f"Snippet: {v['snippet']}\n"
            f"Pattern matched: {v['matched_pattern']}{repeat_note}\n\n"
            f"ECOA (Regulation B, 12 CFR 1002) prohibits inquiries about protected "
            f"characteristics during the lending process. Review content and retrain "
            f"the responsible party. If this was an AI response, escalate to engineering "
            f"for prompt guardrail review."
        )

        _ecoa_title = f"ECOA: {category_label} -- {v['source_label']}"[:200]
        _ecoa_desc = description[:2000]
        _ecoa_sev = v["severity"]
        def _do_ecoa_alert(t=_ecoa_title, d=_ecoa_desc, sev=_ecoa_sev):
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, organization_id, alert_type, severity, title,
                     description, status, created_at)
                VALUES
                    (NULL, :org_id, 'ECOA_VIOLATION', :severity,
                     :title, :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "org_id": organization_id,
                "severity": sev,
                "title": t,
                "desc": d,
            })
        if gateway:
            gateway.propose("create_compliance_alert", _do_ecoa_alert, target_entity=None, target_id=None, description=_ecoa_title[:200],
                payload={"org_id": organization_id, "severity": _ecoa_sev, "title": _ecoa_title, "desc": _ecoa_desc})
        else:
            _do_ecoa_alert()
        actions += 1

        # Create remediation task for the LO if user_id is known
        if v["user_id"]:
            training_resource = _ECOA_CATEGORIES[v["category"]]["training"]

            # Only create task if one doesn't exist for this user+category recently
            existing_task = db.execute(text("""
                SELECT id FROM tasks
                WHERE organization_id = :org_id
                  AND owner_id = :user_id
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
                escalation_note = (
                    "This is a repeat finding -- management escalation may follow."
                    if prior_offenses > 0 else ""
                )
                _ecoa_task_title = f"ECOA remediation: {v['category'].replace('_', ' ')} training required"[:200]
                _ecoa_task_desc = (
                    f"An ECOA compliance scan detected a potential "
                    f"{category_label.lower()} violation in a "
                    f"{v['source_label'].lower()}.\n\n"
                    f"Required action: Complete training module -- {training_resource}.\n"
                    f"{escalation_note}"
                )[:2000]
                _ecoa_task_owner = str(v["user_id"])
                _ecoa_task_pri = priority
                def _do_ecoa_task(t=_ecoa_task_title, d=_ecoa_task_desc, oid=_ecoa_task_owner, p=_ecoa_task_pri):
                    db.execute(text("""
                        INSERT INTO tasks
                            (title, description, owner_id, priority, status,
                             due_date, created_at, organization_id)
                        VALUES
                            (:title, :desc, :owner_id, :priority, 'pending',
                             CURRENT_DATE + 3, CURRENT_TIMESTAMP, :org_id)
                    """), {
                        "title": t,
                        "desc": d,
                        "owner_id": oid,
                        "priority": p,
                        "org_id": organization_id,
                    })
                if gateway:
                    gateway.propose("create_task", _do_ecoa_task, target_entity="user", target_id=_ecoa_task_owner, description=_ecoa_task_title[:200],
                        payload={"title": _ecoa_task_title, "desc": _ecoa_task_desc, "owner_id": _ecoa_task_owner, "priority": _ecoa_task_pri, "org_id": organization_id})
                else:
                    _do_ecoa_task()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"ECOA audit commit failed for org {organization_id}: {e}")

    return {
        "summary": (
            f"{actions} ECOA alert(s) created across "
            f"{len(violations_by_category)} categor{'y' if len(violations_by_category) == 1 else 'ies'}"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "violations_by_category": violations_by_category,
        "repeat_offenders": {uid: cnt for uid, cnt in repeat_offender_history.items()},
        "segments_scanned": len(text_segments),
    }


# ============================================================================
# 3. TCPA Compliance Scanner
# ============================================================================

@autonomous_agent(
    name="tcpa_compliance_scanner",
    description="Verify quiet hours and opt-out compliance for calls/SMS",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=90,
)
def tcpa_compliance_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Check calls/SMS against borrower timezone quiet hours, DNC lists,
    frequency caps, and consent requirements. Produce per-LO compliance scores.

    TCPA (47 USC 227) requires:
    - No calls/texts before 8am or after 9pm in the RECIPIENT's timezone
    - Respect DNC/opt-out requests immediately
    - No more than 3 call attempts per day to the same number
    - Express written consent for marketing messages

    Violations carry penalties of $500-$1,500 per occurrence.
    """
    actions = 0
    lo_violations: Dict[int, Dict[str, int]] = {}  # lo_id -> {type: count}

    # Load org-level compliance directives (e.g., stricter quiet hours)
    org_ctx = get_org_directives(db, organization_id)

    # ---- 1. Quiet-hours violations by borrower timezone -------------------
    # Check lead-based contacts
    lead_contacts = db.execute(text("""
        SELECT a.id, a.lead_id, a.type, a.created_at,
               l.owner_id AS lo_id,
               COALESCE(l.state, '') AS lead_state,
               CONCAT(l.first_name, ' ', l.last_name) AS lead_name,
               l.phone AS lead_phone
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('Call', 'SMS')
        ORDER BY a.created_at DESC
        LIMIT 500
    """), {"org_id": organization_id}).fetchall()

    # Check loan-based contacts
    loan_contacts = db.execute(text("""
        SELECT a.id, a.loan_id, a.type, a.created_at,
               ln.loan_officer_id AS lo_id,
               COALESCE(ln.property_state, '') AS state,
               ln.borrower_name AS contact_name,
               ln.borrower_phone AS phone
        FROM activities a
        JOIN loans ln ON ln.id = a.loan_id AND ln.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
          AND a.type IN ('Call', 'SMS')
        ORDER BY a.created_at DESC
        LIMIT 200
    """), {"org_id": organization_id}).fetchall()

    after_hours_violations: List[Dict[str, Any]] = []

    def _check_quiet_hours(
        activity_id: int, lo_id: Optional[int], act_type: str,
        created_at: Any, state_code: str, contact_name: str, tz_name: str,
    ) -> None:
        """Check if a contact occurred outside TCPA quiet hours."""
        if not created_at:
            return
        offset = _utc_offset_hours(tz_name)
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
                "contact_name": contact_name or "Unknown",
            })
            if lo_id:
                lo_violations.setdefault(lo_id, {}).setdefault("quiet_hours", 0)
                lo_violations[lo_id]["quiet_hours"] += 1

    for row in lead_contacts:
        state_code = (row[5] or "").strip().upper()
        tz_name = _STATE_TIMEZONE.get(state_code, org_timezone)
        _check_quiet_hours(row[0], row[4], row[2], row[3], state_code, row[6], tz_name)

    for row in loan_contacts:
        state_code = (row[5] or "").strip().upper()
        tz_name = _STATE_TIMEZONE.get(state_code, org_timezone)
        _check_quiet_hours(row[0], row[4], row[2], row[3], state_code, row[6], tz_name)

    # Create per-violation alerts for quiet hours (cap at 20)
    for v in after_hours_violations[:20]:
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id
              AND alert_type = 'TCPA_QUIET_HOURS'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {
            "org_id": organization_id,
            "pattern": f"%activity_id={v['activity_id']}%",
        }).fetchone()

        if not existing:
            _tcpa_qh_title = (
                f"TCPA quiet hours: {v['type']} at {v['local_hour']}:00 local "
                f"({v['state']})"
            )[:200]
            _tcpa_qh_desc = (
                f"activity_id={v['activity_id']} | {v['type']} to {v['contact_name']} "
                f"at {v['local_hour']}:00 local time ({v['timezone']}). "
                f"TCPA requires contacts only between 8am-9pm in the recipient's "
                f"timezone. Penalty: $500-$1,500 per violation."
            )[:2000]
            def _do_tcpa_qh(t=_tcpa_qh_title, d=_tcpa_qh_desc):
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :org_id, 'TCPA_QUIET_HOURS', 'high',
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "title": t,
                    "desc": d,
                })
            if gateway:
                gateway.propose("create_compliance_alert", _do_tcpa_qh, target_entity=None, target_id=None, description=_tcpa_qh_title[:200],
                    payload={"org_id": organization_id, "title": _tcpa_qh_title, "desc": _tcpa_qh_desc})
            else:
                _do_tcpa_qh()
            actions += 1

    # ---- 2. Opt-out / DNC compliance -------------------------------------
    all_dnc_violations: List[Dict[str, Any]] = []
    seen_dnc_aids: set = set()

    # Check sms_opt_outs table (may not exist in all deployments)
    try:
        opted_out_sms = db.execute(text("""
            SELECT a.id, a.lead_id, l.phone, l.owner_id,
                   CONCAT(l.first_name, ' ', l.last_name) AS lead_name
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

        for row in opted_out_sms:
            aid = row[0]
            if aid not in seen_dnc_aids:
                seen_dnc_aids.add(aid)
                all_dnc_violations.append({
                    "activity_id": aid, "lead_id": row[1], "lo_id": row[3],
                    "lead_name": row[4] or "Unknown", "source": "sms_opt_outs",
                })
                if row[3]:
                    lo_violations.setdefault(row[3], {}).setdefault("dnc", 0)
                    lo_violations[row[3]]["dnc"] += 1
    except Exception as e:
        logger.debug(f"TCPA scanner: sms_opt_outs table not available: {e}")

    # Check channel_preferences DNC flags
    try:
        dnc_contacts = db.execute(text("""
            SELECT a.id, a.lead_id, a.type, l.owner_id,
                   CONCAT(l.first_name, ' ', l.last_name) AS lead_name
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

        for row in dnc_contacts:
            aid = row[0]
            if aid not in seen_dnc_aids:
                seen_dnc_aids.add(aid)
                all_dnc_violations.append({
                    "activity_id": aid, "lead_id": row[1], "lo_id": row[3],
                    "lead_name": row[4] or "Unknown", "source": "channel_preferences",
                })
                if row[3]:
                    lo_violations.setdefault(row[3], {}).setdefault("dnc", 0)
                    lo_violations[row[3]]["dnc"] += 1
    except Exception as e:
        logger.debug(f"TCPA scanner: channel_preferences DNC check failed: {e}")

    # Create DNC violation alerts
    for v in all_dnc_violations:
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id
              AND alert_type = 'TCPA_OPT_OUT'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {
            "org_id": organization_id,
            "pattern": f"%activity_id={v['activity_id']}%",
        }).fetchone()

        if not existing:
            _tcpa_dnc_title = f"TCPA: Contact to DNC/{v['source']} -- {v['lead_name']}"[:200]
            _tcpa_dnc_desc = (
                f"activity_id={v['activity_id']} | Contact to {v['lead_name']} who "
                f"has opted out via {v['source']}. TCPA requires immediate "
                f"compliance with opt-out requests. Penalties: $500-$1,500 per violation."
            )[:2000]
            _tcpa_dnc_lead = v["lead_id"]
            def _do_tcpa_dnc(t=_tcpa_dnc_title, d=_tcpa_dnc_desc, lid=_tcpa_dnc_lead):
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, lead_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :lead_id, :org_id, 'TCPA_OPT_OUT', 'critical',
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "lead_id": lid,
                    "org_id": organization_id,
                    "title": t,
                    "desc": d,
                })
            if gateway:
                gateway.propose("create_compliance_alert", _do_tcpa_dnc, target_entity="lead", target_id=str(_tcpa_dnc_lead), description=_tcpa_dnc_title[:200],
                    payload={"lead_id": _tcpa_dnc_lead, "org_id": organization_id, "title": _tcpa_dnc_title, "desc": _tcpa_dnc_desc})
            else:
                _do_tcpa_dnc()
            actions += 1

    # ---- 3. Frequency violations (>3 calls/day to same lead) -------------
    frequency_violations = db.execute(text("""
        SELECT l.phone, l.owner_id, COUNT(*) AS contact_count,
               CONCAT(l.first_name, ' ', l.last_name) AS lead_name,
               l.id AS lead_id
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
            WHERE organization_id = :org_id
              AND alert_type = 'TCPA_FREQUENCY'
              AND description LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {
            "org_id": organization_id,
            "pattern": f"%phone={phone}%",
        }).fetchone()

        if not existing:
            _tcpa_freq_title = f"TCPA frequency: {count} contacts to {lead_name} in 24h"[:200]
            _tcpa_freq_desc = (
                f"phone={phone} | {count} outbound contacts to {lead_name} in 24 hours "
                f"(limit: 3). Excessive contact frequency increases TCPA exposure "
                f"and may constitute harassment."
            )[:2000]
            _tcpa_freq_lead = lead_id
            def _do_tcpa_freq(t=_tcpa_freq_title, d=_tcpa_freq_desc, lid=_tcpa_freq_lead):
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, lead_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :lead_id, :org_id, 'TCPA_FREQUENCY', 'high',
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "lead_id": lid,
                    "org_id": organization_id,
                    "title": t,
                    "desc": d,
                })
            if gateway:
                gateway.propose("create_compliance_alert", _do_tcpa_freq, target_entity="lead", target_id=str(_tcpa_freq_lead), description=_tcpa_freq_title[:200],
                    payload={"lead_id": _tcpa_freq_lead, "org_id": organization_id, "title": _tcpa_freq_title, "desc": _tcpa_freq_desc})
            else:
                _do_tcpa_freq()
            actions += 1

    # ---- 4. Per-LO compliance score and report ---------------------------
    lo_compliance_scores: Dict[int, float] = {}
    notifications_sent = 0

    for lo_id in lo_violations:
        # Calculate compliant vs total contacts for this LO
        total = db.execute(text("""
            SELECT COUNT(*) FROM activities a
            JOIN leads l ON l.id = a.lead_id
            WHERE a.organization_id = :org_id
              AND l.owner_id = :lo_id
              AND a.created_at >= CURRENT_DATE - INTERVAL '1 day'
              AND a.type IN ('Call', 'SMS')
        """), {"org_id": organization_id, "lo_id": str(lo_id)}).scalar() or 0

        violation_count = sum(lo_violations[lo_id].values())
        compliant = max(0, total - violation_count)
        score = round((compliant / total * 100), 1) if total > 0 else 100.0
        lo_compliance_scores[lo_id] = score

        # Only create per-LO compliance report when score drops below 95%
        if score >= 95:
            continue

        lo_name_row = db.execute(text("""
            SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :id
        """), {"id": str(lo_id)}).fetchone()
        lo_name = lo_name_row[0] if lo_name_row else f"User {lo_id}"

        violation_breakdown = ", ".join(
            f"{k}: {v}" for k, v in lo_violations[lo_id].items()
        )

        severity = "critical" if score < 80 else ("high" if score < 90 else "medium")

        _tcpa_lo_title = f"TCPA compliance score: {lo_name} -- {score}%"[:200]
        _tcpa_lo_desc = (
            f"LO: {lo_name} (user_id={lo_id}) | Compliance score: {score}% | "
            f"Total contacts: {total} | Violations: {violation_count} "
            f"({violation_breakdown})\n\n"
            f"Action required: Review all flagged contacts. Retrain on TCPA "
            f"requirements (quiet hours, DNC lists, frequency caps). "
            f"Scores below 90% require management review."
        )[:2000]
        _tcpa_lo_sev = severity
        _tcpa_lo_id = str(lo_id)
        def _do_tcpa_lo(t=_tcpa_lo_title, d=_tcpa_lo_desc, sev=_tcpa_lo_sev, uid=_tcpa_lo_id):
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, organization_id, alert_type, severity, title,
                     description, status, created_at)
                VALUES
                    (NULL, :org_id, 'TCPA_LO_REPORT', :severity,
                     :title, :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "org_id": organization_id,
                "severity": sev,
                "title": t,
                "desc": d,
            })
        if gateway:
            gateway.propose("create_compliance_alert", _do_tcpa_lo, target_entity="user", target_id=_tcpa_lo_id, description=_tcpa_lo_title[:200],
                payload={"org_id": organization_id, "severity": _tcpa_lo_sev, "title": _tcpa_lo_title, "desc": _tcpa_lo_desc})
        else:
            _do_tcpa_lo()
        actions += 1
        notifications_sent += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"TCPA compliance scanner commit failed for org {organization_id}: {e}")

    return {
        "summary": (
            f"{actions} TCPA alert(s) -- "
            f"{len(after_hours_violations)} quiet-hour, "
            f"{len(all_dnc_violations)} DNC, "
            f"{len(frequency_violations)} frequency"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications_sent,
        "quiet_hours_violations": len(after_hours_violations),
        "dnc_violations": len(all_dnc_violations),
        "frequency_violations": len(frequency_violations),
        "lo_compliance_scores": lo_compliance_scores,
        "contacts_scanned": len(lead_contacts) + len(loan_contacts),
    }


# ============================================================================
# 4. HMDA Data Collector
# ============================================================================

# Stage priority for HMDA: higher number = closer to closing = more urgent
_STAGE_PRIORITY: Dict[str, int] = {
    "CLEAR_TO_CLOSE": 10, "CTC": 10, "CLOSING": 9, "DOCS": 8, "DOCS_OUT": 8,
    "APPROVED": 7, "CONDITIONAL_APPROVAL": 6, "UW_RECEIVED": 5,
    "UNDERWRITING": 5, "SUBMITTED": 4, "PROCESSING": 3, "DISCLOSED": 2,
    "APPLICATION": 1,
}

# Required HMDA fields: (column_name, human_label, query_index)
_HMDA_REQUIRED_FIELDS: List[Tuple[str, str, int]] = [
    ("loan_purpose", "Loan Purpose (purchase, refinance, etc.)", 5),
    ("property_type", "Property Type (single-family, condo, etc.)", 6),
    ("property_address", "Property Address", 7),
    ("amount", "Loan Amount", 8),
    ("loan_type", "Loan Type (conventional, FHA, VA, USDA)", 9),
    ("rate", "Interest Rate", 10),
    ("application_date", "Application Date", 11),
]

# Optional HMDA fields: useful for census tract / LAR reporting
_HMDA_OPTIONAL_FIELDS: List[Tuple[str, str, int]] = [
    ("property_state", "Property State", 12),
    ("property_county", "Property County (for census tract)", 13),
]


@autonomous_agent(
    name="hmda_data_collector",
    description="Ensure HMDA-reportable data fields are complete on all loans",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=90,
)
def hmda_data_collector(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Check all HMDA-required fields on active loans, calculate completeness
    percentages, prioritize by stage proximity to closing, group by LO, and
    create ONE batch remediation task per LO listing all their incomplete loans.

    HMDA (Home Mortgage Disclosure Act, 12 USC 2801) requires lenders to report
    specific data fields on virtually all mortgage applications. Incomplete data
    risks regulatory penalties and examination findings.
    """
    actions = 0

    # -- Fetch all active non-terminal loans with HMDA-relevant columns ----
    active_loans = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.stage,
               l.loan_purpose, l.property_type, l.property_address, l.amount,
               l.loan_type, l.rate, l.application_date,
               l.property_state, l.property_county
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN """ + _TERMINAL_SQL + """
        ORDER BY l.stage, l.closing_date ASC NULLS LAST
        LIMIT 200
    """), {"org_id": organization_id}).fetchall()

    if not active_loans:
        return {
            "summary": "No active loans to check",
            "actions_taken": 0,
            "notifications_sent": 0,
            "org_readiness_pct": 100.0,
            "total_loans_checked": 0,
        }

    # -- Analyze each loan's HMDA completeness -----------------------------
    lo_incomplete_loans: Dict[int, List[Dict[str, Any]]] = {}
    total_fields = 0
    total_present = 0
    loans_complete = 0

    for loan in active_loans:
        loan_id = loan[0]
        loan_number = loan[1] or f"ID-{loan_id}"
        borrower_name = loan[2] or "Unknown"
        lo_id = loan[3]
        stage = str(loan[4] or "").upper()

        missing_fields: List[str] = []
        loan_total = 0
        loan_present = 0

        # Check required fields
        for col_name, label, idx in _HMDA_REQUIRED_FIELDS:
            val = loan[idx]
            loan_total += 1
            if val is None or (isinstance(val, (int, float)) and val == 0):
                missing_fields.append(label)
            else:
                loan_present += 1

        # Check optional fields (improve completeness score but not flagged as missing)
        for col_name, label, idx in _HMDA_OPTIONAL_FIELDS:
            val = loan[idx]
            loan_total += 1
            if val is not None and str(val).strip():
                loan_present += 1
            else:
                missing_fields.append(label)

        total_fields += loan_total
        total_present += loan_present
        completeness_pct = round((loan_present / loan_total * 100), 1) if loan_total > 0 else 0.0

        if missing_fields:
            priority_score = _STAGE_PRIORITY.get(stage, 1)
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

    # -- Create per-LO batch remediation tasks -----------------------------
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
            WHERE organization_id = :org_id
              AND owner_id = :lo_id
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
                f"[{loan_info['stage']}] -- {loan_info['completeness_pct']}% complete. "
                f"Missing: {fields_str}"
            )

        more_note = ""
        if len(incomplete_loans) > 15:
            more_note = f"\n  ... and {len(incomplete_loans) - 15} more loan(s)."

        # Determine task priority based on how close loans are to closing
        max_priority = max(l["priority_score"] for l in incomplete_loans)
        task_priority = (
            "high" if max_priority >= 7
            else ("medium" if max_priority >= 4 else "low")
        )

        _hmda_task_title = f"HMDA data batch: {len(incomplete_loans)} loan(s) need data -- {lo_name}"[:200]
        _hmda_task_desc = (
            f"HMDA data completeness audit found {len(incomplete_loans)} loan(s) "
            f"with missing required fields:\n\n"
            + "\n".join(loan_lines)
            + more_note
            + "\n\nHMDA (Home Mortgage Disclosure Act) requires these fields for "
            f"regulatory reporting. Loans are prioritized by proximity to closing."
        )[:2000]
        _hmda_task_lo = str(lo_id)
        _hmda_task_pri = task_priority
        def _do_hmda_task(t=_hmda_task_title, d=_hmda_task_desc, lid=_hmda_task_lo, p=_hmda_task_pri):
            db.execute(text("""
                INSERT INTO tasks
                    (title, description, owner_id, priority, status,
                     due_date, created_at, organization_id)
                VALUES
                    (:title, :desc, :lo_id, :priority, 'pending',
                     CURRENT_DATE + 5, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": t,
                "desc": d,
                "lo_id": lid,
                "priority": p,
                "org_id": organization_id,
            })
        if gateway:
            gateway.propose("create_task", _do_hmda_task, target_entity="user", target_id=_hmda_task_lo, description=_hmda_task_title[:200],
                payload={"title": _hmda_task_title, "desc": _hmda_task_desc, "lo_id": _hmda_task_lo, "priority": _hmda_task_pri, "org_id": organization_id})
        else:
            _do_hmda_task()
        actions += 1

    # -- Org-wide HMDA readiness alert -------------------------------------
    org_readiness = round(
        (total_present / total_fields * 100), 1
    ) if total_fields > 0 else 100.0

    if org_readiness < 95:
        severity = "high" if org_readiness < 80 else "medium"

        # Dedup: only one readiness alert per day
        existing_readiness = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id
              AND alert_type = 'HMDA_READINESS'
              AND created_at > CURRENT_DATE
            LIMIT 1
        """), {"org_id": organization_id}).fetchone()

        if not existing_readiness:
            _hmda_ready_title = f"HMDA readiness: {org_readiness}% org-wide"[:200]
            _hmda_ready_desc = (
                f"Organization HMDA data readiness: {org_readiness}%. "
                f"{loans_complete}/{len(active_loans)} loans fully complete. "
                f"{len(active_loans) - loans_complete} loan(s) need attention across "
                f"{len(lo_incomplete_loans)} LO(s).\n\n"
                f"HMDA examinations review data completeness. Target: 100% on all "
                f"required fields before closing."
            )[:2000]
            _hmda_ready_sev = severity
            def _do_hmda_ready(t=_hmda_ready_title, d=_hmda_ready_desc, sev=_hmda_ready_sev):
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title,
                         description, status, created_at)
                    VALUES
                        (NULL, :org_id, 'HMDA_READINESS', :severity,
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "severity": sev,
                    "title": t,
                    "desc": d,
                })
            if gateway:
                gateway.propose("create_compliance_alert", _do_hmda_ready, target_entity=None, target_id=None, description=_hmda_ready_title[:200],
                    payload={"org_id": organization_id, "severity": _hmda_ready_sev, "title": _hmda_ready_title, "desc": _hmda_ready_desc})
            else:
                _do_hmda_ready()
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"HMDA data collector commit failed for org {organization_id}: {e}")

    return {
        "summary": (
            f"{actions} action(s) -- {loans_complete}/{len(active_loans)} loans "
            f"HMDA-complete, org readiness {org_readiness}%"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "org_readiness_pct": org_readiness,
        "total_loans_checked": len(active_loans),
        "loans_complete": loans_complete,
        "loans_incomplete": len(active_loans) - loans_complete,
        "los_with_incomplete": len(lo_incomplete_loans),
    }


# ============================================================================
# 5. Fair Lending Monitor
# ============================================================================

def _z_score(value: float, mean: float, std: float) -> float:
    """Calculate z-score. Returns 0 if std is 0."""
    if std == 0 or std is None:
        return 0.0
    return (value - mean) / std


def _std_dev(values: List[float]) -> float:
    """Sample standard deviation of a list of floats."""
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
    gateway=None,
) -> Dict[str, Any]:
    """Analyze approval/denial rates, pricing distribution, turnaround time
    variance, and steering indicators across loan officers with statistical
    significance testing.

    Fair lending laws (ECOA + Fair Housing Act) prohibit disparate treatment
    and disparate impact. This agent identifies statistical outliers that
    warrant management review -- it does NOT determine whether discrimination
    has occurred, only that patterns deviate significantly from org norms.

    Thresholds:
    - Denial rate: z-score > 1.96 (95% CI) AND rate > org avg + 10pp AND > 15%
    - Pricing: z-score > 1.96 AND avg rate > org avg + 0.25%
    - Turnaround: z-score > 1.96 AND avg days > org avg + 10 AND > 35 days
    - Steering: LO's % of a gov't loan type > 2x org avg AND > 30% of their book
    """
    actions = 0
    findings: List[Dict[str, Any]] = []

    # ---- 1. Denial rates by loan type and LO -----------------------------
    denial_by_type = db.execute(text("""
        SELECT l.loan_type,
               l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               COUNT(*) AS total,
               COUNT(CASE WHEN l.stage IN ('DENIED','DOES_NOT_QUALIFY') THEN 1 END) AS denied,
               ROUND(
                   COUNT(CASE WHEN l.stage IN ('DENIED','DOES_NOT_QUALIFY') THEN 1 END)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 2
               ) AS denial_rate
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
            lo_id = row[1]
            total = int(row[3])
            denied = int(row[4])

            # Flag: z > 1.96 (95% CI) AND practical significance thresholds
            if z > 1.96 and rate > mean_rate + 10 and rate > 15:
                findings.append({
                    "type": "high_denial_rate",
                    "loan_type": loan_type,
                    "lo_name": lo_name,
                    "lo_id": lo_id,
                    "rate": rate,
                    "mean": round(mean_rate, 1),
                    "z_score": round(z, 2),
                    "total": total,
                    "denied": denied,
                })

                # Dedup: check for existing alert this week
                existing = db.execute(text("""
                    SELECT id FROM compliance_alerts
                    WHERE organization_id = :org_id
                      AND alert_type = 'FAIR_LENDING_DENIAL'
                      AND description LIKE :pattern
                      AND created_at > CURRENT_DATE - 7
                    LIMIT 1
                """), {
                    "org_id": organization_id,
                    "pattern": f"%{lo_name}%{loan_type}%",
                }).fetchone()

                if not existing:
                    _fl_denial_sev = "high" if z > 2.5 else "medium"
                    _fl_denial_title = (
                        f"Fair lending: {lo_name} -- {rate}% denial rate "
                        f"on {loan_type}"
                    )[:200]
                    _fl_denial_desc = (
                        f"LO: {lo_name} | Loan type: {loan_type} | "
                        f"Denial rate: {rate}% ({denied}/{total}) vs org avg "
                        f"{mean_rate:.1f}% | Z-score: {z:.2f} (statistically "
                        f"significant at 95%)\n\n"
                        f"Remediation steps:\n"
                        f"1. Review all denied applications for this LO on "
                        f"{loan_type} loans in the past 90 days\n"
                        f"2. Verify denial reasons are consistently documented "
                        f"and compliant with Adverse Action requirements\n"
                        f"3. Compare underwriting criteria applied vs peer LOs\n"
                        f"4. If pattern persists, conduct second-look review of "
                        f"denied files"
                    )[:2000]
                    def _do_fl_denial(t=_fl_denial_title, d=_fl_denial_desc, sev=_fl_denial_sev):
                        db.execute(text("""
                            INSERT INTO compliance_alerts
                                (loan_id, organization_id, alert_type, severity, title,
                                 description, status, created_at)
                            VALUES
                                (NULL, :org_id, 'FAIR_LENDING_DENIAL', :severity,
                                 :title, :desc, 'open', CURRENT_TIMESTAMP)
                        """), {
                            "org_id": organization_id,
                            "severity": sev,
                            "title": t,
                            "desc": d,
                        })
                    if gateway:
                        gateway.propose("create_compliance_alert", _do_fl_denial, target_entity=None, target_id=None, description=_fl_denial_title[:200],
                            payload={"org_id": organization_id, "severity": _fl_denial_sev, "title": _fl_denial_title, "desc": _fl_denial_desc})
                    else:
                        _do_fl_denial()
                    actions += 1

    # ---- 2. Pricing (rate) distribution analysis -------------------------
    pricing_by_lo = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               l.loan_type,
               AVG(l.rate) AS avg_rate,
               COUNT(*) AS loan_count,
               MIN(l.rate) AS min_rate,
               MAX(l.rate) AS max_rate
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
            lo_id = row[0]
            loan_count = int(row[4])

            # Flag: significantly higher rates (> org avg + 0.25%)
            if z > 1.96 and avg_rate > mean_rate + 0.25:
                findings.append({
                    "type": "pricing_outlier",
                    "loan_type": loan_type,
                    "lo_name": lo_name,
                    "lo_id": lo_id,
                    "avg_rate": round(avg_rate, 4),
                    "org_mean": round(mean_rate, 4),
                    "z_score": round(z, 2),
                    "loan_count": loan_count,
                })

                existing = db.execute(text("""
                    SELECT id FROM compliance_alerts
                    WHERE organization_id = :org_id
                      AND alert_type = 'FAIR_LENDING_PRICING'
                      AND description LIKE :pattern
                      AND created_at > CURRENT_DATE - 7
                    LIMIT 1
                """), {
                    "org_id": organization_id,
                    "pattern": f"%{lo_name}%{loan_type}%",
                }).fetchone()

                if not existing:
                    min_rate = float(row[5] or 0)
                    max_rate = float(row[6] or 0)
                    _fl_pricing_sev = "high" if z > 2.5 else "medium"
                    _fl_pricing_title = (
                        f"Fair lending: Pricing outlier -- {lo_name} "
                        f"on {loan_type}"
                    )[:200]
                    _fl_pricing_desc = (
                        f"LO: {lo_name} | Loan type: {loan_type} | "
                        f"Avg rate: {avg_rate:.3f}% vs org avg {mean_rate:.3f}% | "
                        f"Z-score: {z:.2f}\n"
                        f"Rate range: {min_rate:.3f}% - {max_rate:.3f}% across "
                        f"{loan_count} loans.\n\n"
                        f"Remediation steps:\n"
                        f"1. Audit rate sheets and pricing exceptions used\n"
                        f"2. Verify pricing exceptions have documented business "
                        f"justification\n"
                        f"3. Compare discount point and fee structures with peers\n"
                        f"4. Review for patterns in which borrowers receive "
                        f"above-average pricing"
                    )[:2000]
                    def _do_fl_pricing(t=_fl_pricing_title, d=_fl_pricing_desc, sev=_fl_pricing_sev):
                        db.execute(text("""
                            INSERT INTO compliance_alerts
                                (loan_id, organization_id, alert_type, severity, title,
                                 description, status, created_at)
                            VALUES
                                (NULL, :org_id, 'FAIR_LENDING_PRICING', :severity,
                                 :title, :desc, 'open', CURRENT_TIMESTAMP)
                        """), {
                            "org_id": organization_id,
                            "severity": sev,
                            "title": t,
                            "desc": d,
                        })
                    if gateway:
                        gateway.propose("create_compliance_alert", _do_fl_pricing, target_entity=None, target_id=None, description=_fl_pricing_title[:200],
                            payload={"org_id": organization_id, "severity": _fl_pricing_sev, "title": _fl_pricing_title, "desc": _fl_pricing_desc})
                    else:
                        _do_fl_pricing()
                    actions += 1

    # ---- 3. Turnaround time variance (application to funded) -------------
    turnaround_by_lo = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               l.loan_type,
               AVG(EXTRACT(DAY FROM (
                   COALESCE(l.funded_date, l.stage_changed_at) - l.application_date
               ))) AS avg_days,
               COUNT(*) AS funded_count,
               MIN(EXTRACT(DAY FROM (
                   COALESCE(l.funded_date, l.stage_changed_at) - l.application_date
               ))) AS min_days,
               MAX(EXTRACT(DAY FROM (
                   COALESCE(l.funded_date, l.stage_changed_at) - l.application_date
               ))) AS max_days
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.application_date IS NOT NULL
          AND COALESCE(l.funded_date, l.stage_changed_at) IS NOT NULL
          AND COALESCE(l.funded_date, l.stage_changed_at) >= CURRENT_DATE - 90
          AND l.loan_type IS NOT NULL
        GROUP BY l.loan_officer_id, u.first_name, u.last_name, l.loan_type
        HAVING COUNT(*) >= 2
    """), {"org_id": organization_id}).fetchall()

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
            lo_id = row[0]
            funded_count = int(row[4])

            # Flag: significantly slower AND practically meaningful
            if z > 1.96 and days > mean_days + 10 and days > 35:
                findings.append({
                    "type": "slow_processing",
                    "loan_type": loan_type,
                    "lo_name": lo_name,
                    "lo_id": lo_id,
                    "avg_days": round(days, 1),
                    "org_mean": round(mean_days, 1),
                    "z_score": round(z, 2),
                    "funded_count": funded_count,
                })

                existing = db.execute(text("""
                    SELECT id FROM compliance_alerts
                    WHERE organization_id = :org_id
                      AND alert_type = 'FAIR_LENDING_TIMING'
                      AND description LIKE :pattern
                      AND created_at > CURRENT_DATE - 7
                    LIMIT 1
                """), {
                    "org_id": organization_id,
                    "pattern": f"%{lo_name}%{loan_type}%",
                }).fetchone()

                if not existing:
                    min_days = float(row[5] or 0)
                    max_days = float(row[6] or 0)
                    _fl_timing_sev = "high" if z > 2.5 else "medium"
                    _fl_timing_title = (
                        f"Fair lending: Slow processing -- {lo_name} "
                        f"on {loan_type}"
                    )[:200]
                    _fl_timing_desc = (
                        f"LO: {lo_name} | Loan type: {loan_type} | "
                        f"Avg {days:.0f} days to fund vs org avg "
                        f"{mean_days:.0f} days | Z-score: {z:.2f}\n"
                        f"Range: {min_days:.0f}-{max_days:.0f} days across "
                        f"{funded_count} funded loans.\n\n"
                        f"Remediation steps:\n"
                        f"1. Review processing bottlenecks for this LO's "
                        f"{loan_type} pipeline\n"
                        f"2. Compare stage-to-stage cycle times with peer LOs\n"
                        f"3. Investigate whether certain borrower profiles "
                        f"consistently experience delays\n"
                        f"4. Disparate turnaround times may indicate disparate "
                        f"treatment if correlated with protected characteristics"
                    )[:2000]
                    def _do_fl_timing(t=_fl_timing_title, d=_fl_timing_desc, sev=_fl_timing_sev):
                        db.execute(text("""
                            INSERT INTO compliance_alerts
                                (loan_id, organization_id, alert_type, severity, title,
                                 description, status, created_at)
                            VALUES
                                (NULL, :org_id, 'FAIR_LENDING_TIMING', :severity,
                                 :title, :desc, 'open', CURRENT_TIMESTAMP)
                        """), {
                            "org_id": organization_id,
                            "severity": sev,
                            "title": t,
                            "desc": d,
                        })
                    if gateway:
                        gateway.propose("create_compliance_alert", _do_fl_timing, target_entity=None, target_id=None, description=_fl_timing_title[:200],
                            payload={"org_id": organization_id, "severity": _fl_timing_sev, "title": _fl_timing_title, "desc": _fl_timing_desc})
                    else:
                        _do_fl_timing()
                    actions += 1

    # ---- 4. Steering analysis: LO loan-type distribution -----------------
    lo_type_distribution = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               l.loan_type,
               COUNT(*) AS type_count
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
    lo_type_map: Dict[int, Dict[str, Tuple[int, str]]] = {}  # lo_id -> {type: (count, name)}

    for row in lo_type_distribution:
        lo_id, lo_name, loan_type, count = row[0], row[1], str(row[2]), int(row[3])
        org_type_counts[loan_type] = org_type_counts.get(loan_type, 0) + count
        org_total += count
        lo_type_map.setdefault(lo_id, {})[loan_type] = (count, lo_name)

    if org_total > 0:
        org_type_pct = {lt: (cnt / org_total * 100) for lt, cnt in org_type_counts.items()}

        for lo_id, type_counts in lo_type_map.items():
            lo_total = sum(c for c, _ in type_counts.values())
            if lo_total < 5:
                continue

            for loan_type, (count, lo_name) in type_counts.items():
                lo_pct = (count / lo_total) * 100
                org_pct = org_type_pct.get(loan_type, 0)

                # Flag: LO's distribution for a gov't type is 2x+ org average
                # Only flag government-backed programs (FHA, VA, USDA) which
                # have fair-lending implications if borrowers are steered to them.
                if (lo_pct > org_pct * 2 and lo_pct > 30
                        and loan_type.upper() in ("FHA", "VA", "USDA")):

                    findings.append({
                        "type": "steering_indicator",
                        "lo_name": lo_name,
                        "lo_id": lo_id,
                        "loan_type": loan_type,
                        "lo_pct": round(lo_pct, 1),
                        "org_pct": round(org_pct, 1),
                        "count": count,
                        "lo_total": lo_total,
                    })

                    existing = db.execute(text("""
                        SELECT id FROM compliance_alerts
                        WHERE organization_id = :org_id
                          AND alert_type = 'FAIR_LENDING_STEERING'
                          AND description LIKE :pattern
                          AND created_at > CURRENT_DATE - 7
                        LIMIT 1
                    """), {
                        "org_id": organization_id,
                        "pattern": f"%{lo_name}%{loan_type}%",
                    }).fetchone()

                    if not existing:
                        _fl_steer_title = (
                            f"Fair lending: Potential steering -- {lo_name} "
                            f"-> {loan_type}"
                        )[:200]
                        _fl_steer_desc = (
                            f"LO: {lo_name} | {lo_pct:.1f}% of loans are "
                            f"{loan_type} vs org avg {org_pct:.1f}% "
                            f"({count}/{lo_total} loans).\n\n"
                            f"Steering occurs when borrowers who qualify for "
                            f"conventional financing are directed toward "
                            f"government-backed programs (or vice versa).\n\n"
                            f"Remediation steps:\n"
                            f"1. Audit loan program selection documentation for "
                            f"this LO's {loan_type} borrowers\n"
                            f"2. Verify all borrowers received written comparison "
                            f"of eligible products\n"
                            f"3. Review qualification criteria -- were conventional "
                            f"options presented where applicable?\n"
                            f"4. Compare borrower profiles between this LO and peers"
                        )[:2000]
                        def _do_fl_steer(t=_fl_steer_title, d=_fl_steer_desc):
                            db.execute(text("""
                                INSERT INTO compliance_alerts
                                    (loan_id, organization_id, alert_type, severity, title,
                                     description, status, created_at)
                                VALUES
                                    (NULL, :org_id, 'FAIR_LENDING_STEERING', 'medium',
                                     :title, :desc, 'open', CURRENT_TIMESTAMP)
                            """), {
                                "org_id": organization_id,
                                "title": t,
                                "desc": d,
                            })
                        if gateway:
                            gateway.propose("create_compliance_alert", _do_fl_steer, target_entity=None, target_id=None, description=_fl_steer_title[:200],
                                payload={"org_id": organization_id, "title": _fl_steer_title, "desc": _fl_steer_desc})
                        else:
                            _do_fl_steer()
                        actions += 1

    # ---- 5. Generate summary activity log entry --------------------------
    finding_lines: List[str] = []
    for f in findings[:20]:
        if f["type"] == "high_denial_rate":
            finding_lines.append(
                f"  - {f['lo_name']}: {f['rate']}% denial on {f['loan_type']} "
                f"(z={f['z_score']}, org avg {f['mean']}%)"
            )
        elif f["type"] == "pricing_outlier":
            finding_lines.append(
                f"  - {f['lo_name']}: {f['avg_rate']}% avg rate on {f['loan_type']} "
                f"(z={f['z_score']}, org avg {f['org_mean']}%)"
            )
        elif f["type"] == "slow_processing":
            finding_lines.append(
                f"  - {f['lo_name']}: {f['avg_days']} days avg on {f['loan_type']} "
                f"(z={f['z_score']}, org avg {f['org_mean']} days)"
            )
        elif f["type"] == "steering_indicator":
            finding_lines.append(
                f"  - {f['lo_name']}: {f['lo_pct']}% {f['loan_type']} vs "
                f"org avg {f['org_pct']}%"
            )

    report_content = (
        f"[FAIR LENDING MONITOR] Weekly analysis -- {len(findings)} finding(s).\n"
        f"Checks: denial rates by type, pricing distribution, turnaround time, "
        f"steering indicators (90-day lookback, 95% CI thresholds).\n"
    )
    if finding_lines:
        report_content += "Findings:\n" + "\n".join(finding_lines)
    else:
        report_content += "No statistically significant disparities detected."

    _fl_report = report_content[:2000]
    def _do_fl_activity(c=_fl_report):
        db.execute(text("""
            INSERT INTO activities
                (lead_id, loan_id, type, content, created_at, organization_id)
            VALUES
                (NULL, NULL, 'Note', :content, CURRENT_TIMESTAMP, :org_id)
        """), {"content": c, "org_id": organization_id})
    if gateway:
        gateway.propose("create_activity", _do_fl_activity, target_entity=None, target_id=None, description=_fl_report[:200],
            payload={"content": _fl_report, "org_id": organization_id})
    else:
        _do_fl_activity()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Fair lending monitor commit failed for org {organization_id}: {e}")

    denial_findings = [f for f in findings if f["type"] == "high_denial_rate"]
    pricing_findings = [f for f in findings if f["type"] == "pricing_outlier"]
    timing_findings = [f for f in findings if f["type"] == "slow_processing"]
    steering_findings = [f for f in findings if f["type"] == "steering_indicator"]

    return {
        "summary": (
            f"{actions} fair lending alert(s), "
            f"{len(findings)} statistical finding(s)"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "findings_count": len(findings),
        "findings_by_type": {
            "denial_rate": len(denial_findings),
            "pricing_outlier": len(pricing_findings),
            "slow_processing": len(timing_findings),
            "steering": len(steering_findings),
        },
        "loan_types_analyzed": list(type_groups.keys()) if type_groups else [],
    }
