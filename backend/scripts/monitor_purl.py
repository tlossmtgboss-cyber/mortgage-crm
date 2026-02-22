#!/usr/bin/env python3
"""
PURL System Monitoring Script
=============================
Real-time monitoring dashboard for PURL system health and metrics.

Usage:
    python scripts/monitor_purl.py [--interval 30] [--once]
"""

import logging
import os
import sys
import time
import argparse
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ANSI colors
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'


def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_db_connection():
    """Get database connection"""
    from sqlalchemy import create_engine

    db_url = os.getenv('DATABASE_URL', 'sqlite:///./test_agentic_crm.db')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    return create_engine(db_url)


def get_metrics(engine):
    """Gather all metrics from database"""
    from sqlalchemy import text

    metrics = {}

    with engine.connect() as conn:
        # Workspace counts by status
        try:
            result = conn.execute(text("""
                SELECT status, COUNT(*) as count
                FROM purl_workspaces
                GROUP BY status
            """))
            metrics['workspaces_by_status'] = {r[0]: r[1] for r in result.fetchall()}
        except Exception as e:
            logger.error(f"Error in get_metrics (workspaces_by_status): {e}")
            metrics['workspaces_by_status'] = {}

        # Total workspaces
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM purl_workspaces"))
            metrics['total_workspaces'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (total_workspaces): {e}")
            metrics['total_workspaces'] = 0

        # Active tokens
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM purl_access_tokens WHERE status = 'active'
            """))
            metrics['active_tokens'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (active_tokens): {e}")
            metrics['active_tokens'] = 0

        # Recent sessions (last 24h)
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM purl_sessions
                WHERE started_at > datetime('now', '-1 day')
            """))
            metrics['recent_sessions'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (recent_sessions): {e}")
            metrics['recent_sessions'] = 0

        # Applications by status
        try:
            result = conn.execute(text("""
                SELECT status, COUNT(*) as count
                FROM purl_applications
                GROUP BY status
            """))
            metrics['applications_by_status'] = {r[0]: r[1] for r in result.fetchall()}
        except Exception as e:
            logger.error(f"Error in get_metrics (applications_by_status): {e}")
            metrics['applications_by_status'] = {}

        # Total applications
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM purl_applications"))
            metrics['total_applications'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (total_applications): {e}")
            metrics['total_applications'] = 0

        # Documents uploaded
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM purl_documents"))
            metrics['total_documents'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (total_documents): {e}")
            metrics['total_documents'] = 0

        # Events by status
        try:
            result = conn.execute(text("""
                SELECT status, COUNT(*) as count
                FROM purl_events_outbox
                GROUP BY status
            """))
            metrics['events_by_status'] = {r[0]: r[1] for r in result.fetchall()}
        except Exception as e:
            logger.error(f"Error in get_metrics (events_by_status): {e}")
            metrics['events_by_status'] = {}

        # Failed events
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM purl_events_outbox
                WHERE status = 'failed'
            """))
            metrics['failed_events'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (failed_events): {e}")
            metrics['failed_events'] = 0

        # Recent timeline events
        try:
            result = conn.execute(text("""
                SELECT event_type, title, created_at
                FROM purl_timeline_events
                ORDER BY created_at DESC
                LIMIT 5
            """))
            metrics['recent_timeline'] = [
                {'type': r[0], 'title': r[1], 'time': r[2]}
                for r in result.fetchall()
            ]
        except Exception as e:
            logger.error(f"Error in get_metrics (recent_timeline): {e}")
            metrics['recent_timeline'] = []

        # Audit log count (last hour)
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM purl_audit_log
                WHERE created_at > datetime('now', '-1 hour')
            """))
            metrics['recent_audit_count'] = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error in get_metrics (recent_audit_count): {e}")
            metrics['recent_audit_count'] = 0

    return metrics


def render_dashboard(metrics):
    """Render the monitoring dashboard"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║                     PURL SYSTEM MONITORING DASHBOARD                          ║
║                              {now}                              ║
╚══════════════════════════════════════════════════════════════════════════════╝{Colors.END}

{Colors.BOLD}WORKSPACES{Colors.END}
┌─────────────────────────────────────┐
│ Total: {metrics['total_workspaces']:>5}                          │""")

    for status, count in metrics.get('workspaces_by_status', {}).items():
        color = Colors.GREEN if status in ['active', 'application'] else Colors.DIM
        print(f"│ {color}{status:>15}: {count:>5}{Colors.END}                   │")

    print(f"""└─────────────────────────────────────┘

{Colors.BOLD}ACCESS & SESSIONS{Colors.END}
┌─────────────────────────────────────┐
│ Active Tokens:    {Colors.GREEN}{metrics['active_tokens']:>5}{Colors.END}              │
│ Sessions (24h):   {Colors.BLUE}{metrics['recent_sessions']:>5}{Colors.END}              │
│ Audit Events (1h):{Colors.DIM}{metrics['recent_audit_count']:>5}{Colors.END}              │
└─────────────────────────────────────┘

{Colors.BOLD}APPLICATIONS{Colors.END}
┌─────────────────────────────────────┐
│ Total: {metrics['total_applications']:>5}                          │""")

    for status, count in metrics.get('applications_by_status', {}).items():
        color = Colors.GREEN if status == 'submitted' else Colors.YELLOW if status == 'draft' else Colors.DIM
        print(f"│ {color}{status:>15}: {count:>5}{Colors.END}                   │")

    print(f"""└─────────────────────────────────────┘

{Colors.BOLD}DOCUMENTS{Colors.END}
┌─────────────────────────────────────┐
│ Total Uploaded:   {Colors.BLUE}{metrics['total_documents']:>5}{Colors.END}              │
└─────────────────────────────────────┘

{Colors.BOLD}EVENT PROCESSING{Colors.END}
┌─────────────────────────────────────┐""")

    events = metrics.get('events_by_status', {})
    pending = events.get('pending', 0)
    processed = events.get('processed', 0)
    failed = metrics.get('failed_events', 0)

    pending_color = Colors.YELLOW if pending > 10 else Colors.GREEN
    failed_color = Colors.RED if failed > 0 else Colors.GREEN

    print(f"""│ Pending:          {pending_color}{pending:>5}{Colors.END}              │
│ Processed:        {Colors.GREEN}{processed:>5}{Colors.END}              │
│ Failed:           {failed_color}{failed:>5}{Colors.END}              │
└─────────────────────────────────────┘""")

    # Alerts
    alerts = []
    if failed > 0:
        alerts.append(f"{Colors.RED}⚠ {failed} failed events require attention{Colors.END}")
    if pending > 50:
        alerts.append(f"{Colors.YELLOW}⚠ High pending event count: {pending}{Colors.END}")

    if alerts:
        print(f"\n{Colors.BOLD}ALERTS{Colors.END}")
        print("┌─────────────────────────────────────────────────────────────────────────────┐")
        for alert in alerts:
            print(f"│ {alert:<77} │")
        print("└─────────────────────────────────────────────────────────────────────────────┘")

    # Recent activity
    timeline = metrics.get('recent_timeline', [])
    if timeline:
        print(f"\n{Colors.BOLD}RECENT ACTIVITY{Colors.END}")
        print("┌─────────────────────────────────────────────────────────────────────────────┐")
        for event in timeline[:5]:
            title = event['title'][:50] if event['title'] else 'N/A'
            print(f"│ {Colors.DIM}{event['type']:>15}{Colors.END} │ {title:<55} │")
        print("└─────────────────────────────────────────────────────────────────────────────┘")

    print(f"\n{Colors.DIM}Press Ctrl+C to exit{Colors.END}")


def main():
    parser = argparse.ArgumentParser(description='PURL System Monitor')
    parser.add_argument('--interval', type=int, default=30,
                       help='Refresh interval in seconds (default: 30)')
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit')
    args = parser.parse_args()

    # Load environment
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

    engine = get_db_connection()

    try:
        while True:
            clear_screen()
            metrics = get_metrics(engine)
            render_dashboard(metrics)

            if args.once:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n{Colors.GREEN}Monitoring stopped.{Colors.END}")
        sys.exit(0)


if __name__ == '__main__':
    main()
