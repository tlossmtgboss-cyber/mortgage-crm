#!/bin/bash
# BlueBubbles health check — run via cron every 60 seconds
BB_URL="http://localhost:1234"
BB_PASS="${IMESSAGE_BB_PASSWORD:-01Woodwindow2026!}"
FAIL_FILE="/tmp/bb_health_failures"

response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BB_URL/api/v1/ping?password=$BB_PASS")

if [ "$response" != "200" ]; then
    count=$(cat "$FAIL_FILE" 2>/dev/null || echo 0)
    count=$((count + 1))
    echo $count > "$FAIL_FILE"

    if [ $count -ge 3 ]; then
        echo "$(date): BlueBubbles CRITICAL - $count consecutive failures" >> /tmp/bb_health.log
        # Could add notification here (email, webhook, etc.)
    fi
else
    echo 0 > "$FAIL_FILE"
fi
