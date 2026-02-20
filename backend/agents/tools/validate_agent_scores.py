"""
Perennia AI - Agent Score Validation Script
=============================================
Validates that all 20 agents have the required configuration for A-grade (90+) scores.
Checks: system prompts, compliance rules, tool guidelines, TD methodology, outbound gates.

Usage:
    python backend/agents/tools/validate_agent_scores.py
"""

import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Resolve project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # backend/agents/tools -> project root
PROMPTS_DIR = PROJECT_ROOT / "backend" / "agents" / "perennia-prompts"
TOOLS_DIR = PROJECT_ROOT / "backend" / "agents" / "tools"

# ─── Agent Registry (mirrors u_agent_challenge.py) ───
AGENTS = {
    # Core CRM
    "pipeline_analyst":      {"prompt": "core/pipeline_analyst_core.md",      "category": "core_crm",     "outbound": False},
    "compliance_checker":    {"prompt": "core/compliance_checker_core.md",    "category": "core_crm",     "outbound": False},
    "lead_nurturer":         {"prompt": "core/lead_agent_core.md",           "category": "core_crm",     "outbound": True},
    "document_tracker":      {"prompt": "core/document_agent_core.md",       "category": "core_crm",     "outbound": False},
    "profitability_analyst": {"prompt": "core/profitability_analyst_core.md", "category": "core_crm",     "outbound": False},
    "rate_advisor":          {"prompt": "core/rate_advisor_core.md",         "category": "core_crm",     "outbound": False},
    "team_coach":            {"prompt": "core/team_coach_core.md",           "category": "core_crm",     "outbound": False},
    "customer_intelligence": {"prompt": "core/customer_intelligence_core.md","category": "core_crm",     "outbound": False},
    # Communication
    "voice_os":              {"prompt": "core/voice_os_core.md",             "category": "communication", "outbound": True},
    "uvip":                  {"prompt": "core/uvip_core.md",                 "category": "communication", "outbound": False},
    "email_intelligence":    {"prompt": "core/email_intel_core.md",          "category": "communication", "outbound": False},
    "ai_receptionist":       {"prompt": "conditional/ai_receptionist_sam.md","category": "communication", "outbound": True},
    # Operations
    "smart_scheduler":       {"prompt": "core/smart_scheduler_core.md",      "category": "operations",    "outbound": False},
    "task_automation":        {"prompt": "core/task_automation_core.md",      "category": "operations",    "outbound": False},
    "sla_tracker":           {"prompt": "core/sla_tracker_core.md",          "category": "operations",    "outbound": False},
    "integrations":          {"prompt": "core/integrations_core.md",         "category": "operations",    "outbound": False},
    # Business
    "reporting":             {"prompt": "core/reporting_core.md",             "category": "business",      "outbound": False},
    "notifications":         {"prompt": "core/notification_center_core.md",  "category": "business",      "outbound": True},
    "subscription":          {"prompt": "core/subscription_manager_core.md", "category": "business",      "outbound": False},
    "onboarding":            {"prompt": "core/onboarding_assistant_core.md", "category": "business",      "outbound": False},
}

# Outbound tool functions that must have compliance gates
OUTBOUND_TOOLS = {
    "voice.py":         ["initiate_outbound_call", "drop_voicemail", "schedule_callback"],
    "notifications.py": ["send_notification", "batch_send"],
    "receptionist.py":  ["create_callback_request"],
}

# Required sections in every agent prompt
REQUIRED_PROMPT_SECTIONS = [
    ("NEVER rules",           r"(?i)\bNEVER\b"),
    ("Tool guidelines",       r"(?i)(tool\s+selection|tool\s+usage|core\s+capabilities)"),
    ("Output format",         r"(?i)(output\s+format|response\s+format)"),
    ("Compliance reference",  r"(?i)(compliance|tcpa|trid|respa|dnc)"),
]

# TD methodology markers
TD_MARKERS = [
    ("Decision Engine",     r"(?i)(decision\s+engine|clarify.*commitment|schedule.*priorities)"),
    ("Communication rules", r"(?i)(communication\s+rules|word\s+efficiency|talk\s+ratio|80/20)"),
]


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def check_prompt_exists(agent_id: str, info: dict) -> Tuple[bool, str]:
    """Check if agent has a dedicated system prompt file."""
    if info["prompt"] is None:
        return False, "No dedicated prompt file configured"
    path = PROMPTS_DIR / info["prompt"]
    if path.exists():
        return True, str(path.relative_to(PROJECT_ROOT))
    return False, f"Missing: {info['prompt']}"


def check_prompt_sections(agent_id: str, info: dict) -> List[Tuple[str, bool]]:
    """Check prompt contains required sections."""
    if info["prompt"] is None:
        return [(name, False) for name, _ in REQUIRED_PROMPT_SECTIONS]

    path = PROMPTS_DIR / info["prompt"]
    if not path.exists():
        return [(name, False) for name, _ in REQUIRED_PROMPT_SECTIONS]

    content = path.read_text()
    results = []
    for name, pattern in REQUIRED_PROMPT_SECTIONS:
        found = bool(re.search(pattern, content))
        results.append((name, found))
    return results


def check_td_methodology(agent_id: str, info: dict) -> List[Tuple[str, bool]]:
    """Check prompt contains TD methodology markers."""
    if info["prompt"] is None:
        return [(name, False) for name, _ in TD_MARKERS]

    path = PROMPTS_DIR / info["prompt"]
    if not path.exists():
        return [(name, False) for name, _ in TD_MARKERS]

    content = path.read_text()
    results = []
    for name, pattern in TD_MARKERS:
        found = bool(re.search(pattern, content))
        results.append((name, found))
    return results


def check_outbound_gates() -> Dict[str, List[Tuple[str, bool]]]:
    """Check that outbound tool functions have compliance gates."""
    results = {}
    gate_patterns = [
        r"_validate_outbound",
        r"validate_outbound_contact",
        r"check_dnc",
        r"_check_sms_compliance",
        r"dnc.*check|DNC",
        r"TCPA|tcpa",
        r"BLOCKED.*DNC|BLOCKED.*calling\s+window",
    ]

    for filename, functions in OUTBOUND_TOOLS.items():
        filepath = TOOLS_DIR / filename
        if not filepath.exists():
            results[filename] = [(fn, False) for fn in functions]
            continue

        content = filepath.read_text()
        file_results = []

        for func_name in functions:
            # Find the function body
            pattern = rf"def {func_name}\(.*?\).*?(?=\ndef |\Z)"
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                file_results.append((func_name, False))
                continue

            func_body = match.group(0)
            has_gate = any(re.search(gp, func_body) for gp in gate_patterns)
            file_results.append((func_name, has_gate))

        results[filename] = file_results
    return results


def check_compliance_utils_exists() -> Tuple[bool, int]:
    """Check compliance_utils.py exists and has the expected tools."""
    path = TOOLS_DIR / "compliance_utils.py"
    if not path.exists():
        return False, 0

    content = path.read_text()
    tool_count = content.count("@mortgage_tool")
    return True, tool_count


def check_compliance_rules_exists() -> Tuple[bool, int]:
    """Check compliance_rules.md exists and has NEVER rules."""
    path = PROMPTS_DIR / "core" / "compliance_rules.md"
    if not path.exists():
        return False, 0

    content = path.read_text()
    never_count = len(re.findall(r"(?i)\bNEVER\b", content))
    return True, never_count


def run_validation():
    """Run full validation and print report."""
    print(f"\n{Colors.BOLD}{'='*70}")
    print("  PERENNIA AI — Agent Score Validation Report")
    print(f"{'='*70}{Colors.END}\n")

    total_checks = 0
    passed_checks = 0
    warnings = []
    failures = []

    # ── 1. Compliance Foundation ──
    print(f"{Colors.BOLD}Phase 1: Compliance Foundation{Colors.END}")
    print("-" * 40)

    cu_exists, cu_tools = check_compliance_utils_exists()
    total_checks += 1
    if cu_exists:
        passed_checks += 1
        print(f"  {Colors.GREEN}✓{Colors.END} compliance_utils.py exists ({cu_tools} tools)")
    else:
        failures.append("compliance_utils.py missing")
        print(f"  {Colors.RED}✗{Colors.END} compliance_utils.py MISSING")

    cr_exists, cr_nevers = check_compliance_rules_exists()
    total_checks += 1
    if cr_exists:
        passed_checks += 1
        print(f"  {Colors.GREEN}✓{Colors.END} compliance_rules.md exists ({cr_nevers} NEVER rules)")
    else:
        failures.append("compliance_rules.md missing")
        print(f"  {Colors.RED}✗{Colors.END} compliance_rules.md MISSING")

    gate_results = check_outbound_gates()
    for filename, func_results in gate_results.items():
        for func_name, has_gate in func_results:
            total_checks += 1
            if has_gate:
                passed_checks += 1
                print(f"  {Colors.GREEN}✓{Colors.END} {filename}:{func_name} has compliance gate")
            else:
                failures.append(f"{filename}:{func_name} missing compliance gate")
                print(f"  {Colors.RED}✗{Colors.END} {filename}:{func_name} MISSING compliance gate")

    # ── 2. System Prompts ──
    print(f"\n{Colors.BOLD}Phase 2: System Prompts{Colors.END}")
    print("-" * 40)

    prompt_exists_count = 0
    for agent_id, info in AGENTS.items():
        exists, detail = check_prompt_exists(agent_id, info)
        total_checks += 1
        if exists:
            passed_checks += 1
            prompt_exists_count += 1
            print(f"  {Colors.GREEN}✓{Colors.END} {agent_id}: {detail}")
        else:
            if info["prompt"] is None:
                warnings.append(f"{agent_id}: no dedicated prompt")
                print(f"  {Colors.YELLOW}△{Colors.END} {agent_id}: {detail}")
            else:
                failures.append(f"{agent_id}: prompt file missing")
                print(f"  {Colors.RED}✗{Colors.END} {agent_id}: {detail}")

    # ── 3. Prompt Content Checks ──
    print(f"\n{Colors.BOLD}Phase 3: Prompt Content Validation{Colors.END}")
    print("-" * 40)

    section_coverage = {name: 0 for name, _ in REQUIRED_PROMPT_SECTIONS}
    td_coverage = {name: 0 for name, _ in TD_MARKERS}
    agents_with_prompts = sum(1 for info in AGENTS.values() if info["prompt"] is not None)

    for agent_id, info in AGENTS.items():
        if info["prompt"] is None:
            continue

        sections = check_prompt_sections(agent_id, info)
        td_checks = check_td_methodology(agent_id, info)
        all_sections_pass = all(found for _, found in sections)
        all_td_pass = all(found for _, found in td_checks)

        for name, found in sections:
            total_checks += 1
            if found:
                passed_checks += 1
                section_coverage[name] += 1

        for name, found in td_checks:
            total_checks += 1
            if found:
                passed_checks += 1
                td_coverage[name] += 1

        status = Colors.GREEN + "✓" if all_sections_pass and all_td_pass else Colors.YELLOW + "△" if all_sections_pass else Colors.RED + "✗"
        missing = [n for n, f in sections + td_checks if not f]
        if missing:
            print(f"  {status}{Colors.END} {agent_id}: missing [{', '.join(missing)}]")
        else:
            print(f"  {status}{Colors.END} {agent_id}: all sections present")

    # ── Coverage Summary ──
    print(f"\n{Colors.BOLD}Coverage Summary{Colors.END}")
    print("-" * 40)

    for name, count in section_coverage.items():
        pct = round(count / agents_with_prompts * 100) if agents_with_prompts > 0 else 0
        color = Colors.GREEN if pct >= 90 else Colors.YELLOW if pct >= 70 else Colors.RED
        print(f"  {color}{pct:3d}%{Colors.END} {name} ({count}/{agents_with_prompts} agents)")

    for name, count in td_coverage.items():
        pct = round(count / agents_with_prompts * 100) if agents_with_prompts > 0 else 0
        color = Colors.GREEN if pct >= 90 else Colors.YELLOW if pct >= 70 else Colors.RED
        print(f"  {color}{pct:3d}%{Colors.END} {name} ({count}/{agents_with_prompts} agents)")

    # ── Dimension Score Estimates ──
    print(f"\n{Colors.BOLD}Estimated Dimension Impact{Colors.END}")
    print("-" * 40)

    compliance_gate_pct = sum(1 for fr in gate_results.values() for _, has in fr if has) / max(1, sum(len(fr) for fr in gate_results.values())) * 100
    prompt_pct = prompt_exists_count / len(AGENTS) * 100
    never_pct = section_coverage.get("NEVER rules", 0) / max(1, agents_with_prompts) * 100
    tool_guide_pct = section_coverage.get("Tool guidelines", 0) / max(1, agents_with_prompts) * 100
    td_pct = td_coverage.get("Decision Engine", 0) / max(1, agents_with_prompts) * 100

    dimensions = [
        ("Accuracy",     tool_guide_pct,       "Tool guidelines drive correct data retrieval"),
        ("Compliance",   min(compliance_gate_pct, never_pct), "Outbound gates + NEVER rules"),
        ("Tone",         td_pct,               "TD methodology + Decision Engine"),
        ("Tool Usage",   tool_guide_pct,       "Tool selection guidelines in prompts"),
        ("Efficiency",   prompt_pct,           "Dedicated prompts reduce token waste"),
        ("Adaptability", prompt_pct,           "Identity sections define pivoting behavior"),
    ]

    for dim, score, reason in dimensions:
        color = Colors.GREEN if score >= 90 else Colors.YELLOW if score >= 70 else Colors.RED
        print(f"  {color}{score:5.1f}%{Colors.END} {dim:15s} — {reason}")

    # ── Final Summary ──
    print(f"\n{Colors.BOLD}{'='*70}")
    pass_rate = round(passed_checks / total_checks * 100) if total_checks > 0 else 0
    color = Colors.GREEN if pass_rate >= 90 else Colors.YELLOW if pass_rate >= 70 else Colors.RED
    print(f"  TOTAL: {color}{passed_checks}/{total_checks} checks passed ({pass_rate}%){Colors.END}")
    print(f"  Failures: {len(failures)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"{'='*70}{Colors.END}\n")

    if failures:
        print(f"{Colors.RED}Failures:{Colors.END}")
        for f in failures:
            print(f"  - {f}")

    if warnings:
        print(f"\n{Colors.YELLOW}Warnings:{Colors.END}")
        for w in warnings:
            print(f"  - {w}")

    print()
    return len(failures) == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
