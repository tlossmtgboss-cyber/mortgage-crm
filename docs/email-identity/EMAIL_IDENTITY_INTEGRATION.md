# Email Identity Resolution - Integration Guide

This guide provides detailed instructions for integrating the Email Identity Resolution system into your application components.

---

## Table of Contents

1. [Backend API Integration](#1-backend-api-integration)
2. [Frontend React Integration](#2-frontend-react-integration)
3. [Email Sync Services](#3-email-sync-services)
4. [Real-time Updates](#4-real-time-updates)
5. [Dashboard Widgets](#5-dashboard-widgets)
6. [Notification System](#6-notification-system)
7. [Search & Filtering](#7-search--filtering)
8. [Batch Operations](#8-batch-operations)

---

## 1. Backend API Integration

### Adding to Existing Email Endpoints

If you have existing email endpoints, add identity resolution:

```python
# routes/email_routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.email_identity_resolver import get_email_identity_resolver

router = APIRouter()

@router.post("/emails/import")
async def import_email(
    email_data: EmailImportSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Import email with automatic identity resolution."""

    # Get resolver
    resolver = get_email_identity_resolver(db)

    # Resolve identity
    match = resolver.resolve({
        "from_email": email_data.sender,
        "subject": email_data.subject,
        "body_preview": email_data.body[:500],
        "thread_id": email_data.thread_id,
        "to_emails": email_data.recipients,
    }, current_user.id)

    # Create email record with match data
    email_record = EmailReconciliationQueue(
        user_id=current_user.id,
        from_email=email_data.sender,
        subject=email_data.subject,
        # ... other fields ...

        # Identity resolution fields
        matched_contact_id=match["matched_contact_id"],
        matched_loan_id=match["matched_loan_id"],
        matched_lead_id=match["matched_lead_id"],
        match_method=match["match_method"],
        match_confidence=match["match_confidence"],
        match_evidence=match["match_evidence"],
        match_client_name=match["match_client_name"],
        match_loan_number=match["match_loan_number"],
        is_priority=match["is_priority"],
    )

    db.add(email_record)
    db.commit()

    return {
        "id": email_record.id,
        "match": match,
        "status": "queued"
    }
```

### Creating a Stats Endpoint

```python
# routes/email_intelligence_routes.py

@router.get("/email-intelligence/identity-stats")
async def get_identity_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get identity resolution statistics."""

    from services.email_identity_analytics import EmailIdentityAnalytics

    analytics = EmailIdentityAnalytics(db)
    stats = analytics.get_match_statistics(current_user.id, days=days)

    return {
        "period_days": days,
        "total_emails": stats.total_emails,
        "matched": stats.matched,
        "unmatched": stats.unmatched,
        "match_rate": stats.match_rate,
        "avg_confidence": stats.avg_confidence,
        "priority_count": stats.priority_count,
        "by_method": stats.by_method,
    }
```

### Adding Health Check Endpoint

```python
@router.get("/email-intelligence/health")
async def check_identity_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check email identity resolution health."""

    from services.email_identity_analytics import MonitoringAlerts

    monitor = MonitoringAlerts(db)
    health = monitor.run_health_check(current_user.id)

    return health
```

---

## 2. Frontend React Integration

### Email List Component with Match Indicators

```tsx
// components/EmailList.tsx

import React from 'react';
import { Badge, Tooltip } from '@/components/ui';

interface EmailMatch {
  matched_contact_id?: number;
  matched_loan_id?: number;
  matched_lead_id?: number;
  match_method?: string;
  match_confidence?: number;
  match_client_name?: string;
  match_loan_number?: string;
  is_priority: boolean;
  vendor_type?: string;
}

interface Email {
  id: number;
  from_email: string;
  subject: string;
  received_date: string;
  match?: EmailMatch;
}

const MatchConfidenceBadge: React.FC<{ confidence: number }> = ({ confidence }) => {
  const color = confidence >= 0.9 ? 'green' : confidence >= 0.7 ? 'yellow' : 'gray';
  return (
    <Badge color={color}>
      {Math.round(confidence * 100)}%
    </Badge>
  );
};

const MatchMethodBadge: React.FC<{ method: string }> = ({ method }) => {
  const labels: Record<string, string> = {
    known_client_email: 'Known Client',
    lead_email_match: 'Lead',
    loan_email_match: 'Loan',
    contact_email_match: 'Contact',
    loan_number_subject: 'Loan #',
    thread_continuity: 'Thread',
    domain_vendor_match: 'Vendor',
  };
  return <Badge variant="outline">{labels[method] || method}</Badge>;
};

export const EmailListItem: React.FC<{ email: Email }> = ({ email }) => {
  const { match } = email;

  return (
    <div className={`email-item ${match?.is_priority ? 'priority' : ''}`}>
      <div className="email-header">
        <span className="from">{email.from_email}</span>

        {match?.is_priority && (
          <Badge color="red" className="ml-2">Priority</Badge>
        )}

        {match?.match_method && (
          <div className="match-indicators ml-auto">
            <MatchMethodBadge method={match.match_method} />
            {match.match_confidence && (
              <MatchConfidenceBadge confidence={match.match_confidence} />
            )}
          </div>
        )}
      </div>

      <div className="email-subject">{email.subject}</div>

      {match?.match_client_name && (
        <div className="match-info text-sm text-gray-500">
          <Tooltip content={`Matched via ${match.match_method}`}>
            <span>→ {match.match_client_name}</span>
          </Tooltip>
          {match.match_loan_number && (
            <span className="ml-2">Loan #{match.match_loan_number}</span>
          )}
        </div>
      )}

      {match?.vendor_type && (
        <Badge color="purple" size="sm">
          Vendor: {match.match_client_name}
        </Badge>
      )}
    </div>
  );
};
```

### Priority Inbox Component

```tsx
// components/PriorityInbox.tsx

import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchPriorityEmails } from '@/api/emails';

export const PriorityInbox: React.FC = () => {
  const { data: emails, isLoading } = useQuery({
    queryKey: ['priorityEmails'],
    queryFn: () => fetchPriorityEmails(),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (isLoading) return <div>Loading priority emails...</div>;

  const priorityEmails = emails?.filter(e => e.match?.is_priority) || [];

  return (
    <div className="priority-inbox">
      <h2 className="text-lg font-semibold mb-4">
        Priority Emails ({priorityEmails.length})
      </h2>

      {priorityEmails.length === 0 ? (
        <p className="text-gray-500">No priority emails</p>
      ) : (
        <div className="space-y-2">
          {priorityEmails.map(email => (
            <PriorityEmailCard key={email.id} email={email} />
          ))}
        </div>
      )}
    </div>
  );
};

const PriorityEmailCard: React.FC<{ email: Email }> = ({ email }) => {
  return (
    <div className="p-4 border-l-4 border-red-500 bg-red-50 rounded">
      <div className="font-medium">{email.match?.match_client_name}</div>
      <div className="text-sm">{email.subject}</div>
      <div className="text-xs text-gray-500 mt-1">
        {email.match?.match_loan_number && `Loan #${email.match.match_loan_number}`}
      </div>
    </div>
  );
};
```

### Match Statistics Dashboard

```tsx
// components/IdentityStatsDashboard.tsx

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { PieChart, BarChart } from '@/components/charts';

interface IdentityStats {
  total_emails: number;
  matched: number;
  unmatched: number;
  match_rate: number;
  avg_confidence: number;
  priority_count: number;
  by_method: Record<string, number>;
}

export const IdentityStatsDashboard: React.FC<{ days?: number }> = ({ days = 7 }) => {
  const { data: stats, isLoading } = useQuery<IdentityStats>({
    queryKey: ['identityStats', days],
    queryFn: () => fetch(`/api/v1/email-intelligence/identity-stats?days=${days}`)
      .then(r => r.json()),
  });

  if (isLoading || !stats) return <div>Loading...</div>;

  const methodData = Object.entries(stats.by_method).map(([method, count]) => ({
    name: formatMethodName(method),
    value: count,
  }));

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Summary Cards */}
      <div className="col-span-2 grid grid-cols-4 gap-4">
        <StatCard
          title="Total Emails"
          value={stats.total_emails}
        />
        <StatCard
          title="Match Rate"
          value={`${stats.match_rate.toFixed(1)}%`}
          trend={stats.match_rate >= 75 ? 'up' : 'down'}
        />
        <StatCard
          title="Avg Confidence"
          value={`${(stats.avg_confidence * 100).toFixed(0)}%`}
        />
        <StatCard
          title="Priority Emails"
          value={stats.priority_count}
          highlight
        />
      </div>

      {/* Match Rate Pie Chart */}
      <div className="bg-white p-4 rounded-lg shadow">
        <h3 className="font-semibold mb-4">Match Distribution</h3>
        <PieChart
          data={[
            { name: 'Matched', value: stats.matched, color: '#22c55e' },
            { name: 'Unmatched', value: stats.unmatched, color: '#ef4444' },
          ]}
        />
      </div>

      {/* Method Breakdown */}
      <div className="bg-white p-4 rounded-lg shadow">
        <h3 className="font-semibold mb-4">Match Methods</h3>
        <BarChart data={methodData} />
      </div>
    </div>
  );
};

const formatMethodName = (method: string): string => {
  const names: Record<string, string> = {
    known_client_email: 'Known Client',
    lead_email_match: 'Lead Match',
    loan_email_match: 'Loan Match',
    contact_email_match: 'Contact',
    loan_number_subject: 'Loan Number',
    thread_continuity: 'Thread',
    domain_vendor_match: 'Vendor',
  };
  return names[method] || method;
};
```

---

## 3. Email Sync Services

### Gmail Sync Integration

```python
# services/gmail_sync.py

from services.email_identity_resolver import get_email_identity_resolver

class GmailSyncService:
    """Gmail sync service with identity resolution."""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.resolver = get_email_identity_resolver(db)

    async def sync_messages(self, messages: List[dict]) -> dict:
        """Sync Gmail messages with identity resolution."""

        results = {
            "total": len(messages),
            "synced": 0,
            "matched": 0,
            "priority": 0,
            "errors": 0,
        }

        for message in messages:
            try:
                # Extract email data
                email_data = self._extract_email_data(message)

                # Resolve identity
                match = self.resolver.resolve(email_data, self.user_id)

                # Create/update record
                await self._save_email(message, email_data, match)

                results["synced"] += 1
                if match["match_method"]:
                    results["matched"] += 1
                if match["is_priority"]:
                    results["priority"] += 1

            except Exception as e:
                logger.error(f"Sync error for message {message.get('id')}: {e}")
                results["errors"] += 1

        return results

    def _extract_email_data(self, message: dict) -> dict:
        """Extract email data from Gmail API format."""
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}

        return {
            "from_email": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "body_preview": message.get("snippet", ""),
            "thread_id": message.get("threadId"),
            "to_emails": self._parse_recipients(headers.get("To", "")),
            "cc_emails": self._parse_recipients(headers.get("Cc", "")),
        }
```

### Microsoft Graph Sync Integration

```python
# services/ms_graph_sync.py

class MicrosoftGraphSyncService:
    """Microsoft Graph email sync with identity resolution."""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.resolver = get_email_identity_resolver(db)

    async def sync_message(self, graph_message: dict) -> dict:
        """Sync a single Microsoft Graph message."""

        # The resolver handles Graph format natively
        email_data = {
            "from": graph_message.get("from"),
            "subject": graph_message.get("subject"),
            "body_preview": graph_message.get("bodyPreview", ""),
            "thread_id": graph_message.get("conversationId"),
            "to": graph_message.get("toRecipients", []),
            "cc": graph_message.get("ccRecipients", []),
        }

        match = self.resolver.resolve(email_data, self.user_id)

        return {
            "graph_id": graph_message.get("id"),
            "match": match,
            "is_priority": match["is_priority"],
        }
```

---

## 4. Real-time Updates

### WebSocket Integration

```python
# services/realtime.py

from fastapi import WebSocket
from typing import Dict, Set
import json

class EmailIdentityWebSocket:
    """WebSocket manager for real-time email identity updates."""

    def __init__(self):
        self.connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.connections:
            self.connections[user_id].discard(websocket)

    async def notify_new_email(self, user_id: int, email_data: dict, match: dict):
        """Notify user of new email with match data."""

        if user_id not in self.connections:
            return

        message = json.dumps({
            "type": "new_email",
            "email": email_data,
            "match": match,
            "is_priority": match["is_priority"],
        })

        for ws in self.connections[user_id]:
            try:
                await ws.send_text(message)
            except Exception:
                pass  # Handle disconnected sockets

    async def notify_priority_email(self, user_id: int, email_data: dict, match: dict):
        """Send priority notification."""

        if not match["is_priority"]:
            return

        message = json.dumps({
            "type": "priority_alert",
            "email": email_data,
            "client_name": match["match_client_name"],
            "loan_number": match["match_loan_number"],
        })

        for ws in self.connections.get(user_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                pass

# WebSocket endpoint
@app.websocket("/ws/emails/{user_id}")
async def email_websocket(websocket: WebSocket, user_id: int):
    manager = EmailIdentityWebSocket()
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
```

### Frontend WebSocket Hook

```tsx
// hooks/useEmailWebSocket.ts

import { useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/components/ui';

export const useEmailWebSocket = (userId: number) => {
  const queryClient = useQueryClient();

  useEffect(() => {
    const ws = new WebSocket(`ws://your-api/ws/emails/${userId}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'new_email') {
        // Invalidate email queries
        queryClient.invalidateQueries(['emails']);

        if (data.is_priority) {
          toast({
            title: 'Priority Email',
            description: `From ${data.match.match_client_name}`,
            variant: 'urgent',
          });
        }
      }

      if (data.type === 'priority_alert') {
        // Show priority notification
        toast({
          title: '⚡ Priority Email!',
          description: `${data.client_name} - ${data.email.subject}`,
          variant: 'urgent',
          duration: 10000,
        });
      }
    };

    return () => ws.close();
  }, [userId, queryClient]);
};
```

---

## 5. Dashboard Widgets

### Match Rate Widget

```tsx
// components/widgets/MatchRateWidget.tsx

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { CircularProgress } from '@/components/ui';

export const MatchRateWidget: React.FC = () => {
  const { data } = useQuery({
    queryKey: ['matchRate'],
    queryFn: () => fetch('/api/v1/email-intelligence/identity-stats?days=1')
      .then(r => r.json()),
    refetchInterval: 60000,
  });

  const rate = data?.match_rate || 0;
  const color = rate >= 80 ? 'green' : rate >= 60 ? 'yellow' : 'red';

  return (
    <div className="widget">
      <h3>Today's Match Rate</h3>
      <CircularProgress value={rate} color={color} />
      <p>{rate.toFixed(1)}%</p>
      <p className="text-sm text-gray-500">
        {data?.matched || 0} of {data?.total_emails || 0} emails matched
      </p>
    </div>
  );
};
```

### Priority Email Counter Widget

```tsx
// components/widgets/PriorityCountWidget.tsx

export const PriorityCountWidget: React.FC = () => {
  const { data } = useQuery({
    queryKey: ['priorityCount'],
    queryFn: () => fetch('/api/v1/email-intelligence/identity-stats')
      .then(r => r.json()),
    refetchInterval: 30000,
  });

  return (
    <div className="widget bg-red-50 border-l-4 border-red-500">
      <h3>Priority Emails</h3>
      <div className="text-3xl font-bold text-red-600">
        {data?.priority_count || 0}
      </div>
      <p className="text-sm">Awaiting response</p>
    </div>
  );
};
```

---

## 6. Notification System

### Email Notification on Priority Match

```python
# services/notifications.py

from services.email_identity_resolver import get_email_identity_resolver

async def send_priority_notification(
    db: Session,
    user: User,
    email_record: EmailReconciliationQueue,
    match: dict
):
    """Send notification for priority email."""

    if not match["is_priority"]:
        return

    # Get user notification preferences
    prefs = await get_user_notification_preferences(user.id)

    # Build notification content
    content = {
        "title": f"Priority Email from {match['match_client_name']}",
        "body": f"Subject: {email_record.subject}",
        "data": {
            "email_id": email_record.id,
            "loan_number": match["match_loan_number"],
            "client_name": match["match_client_name"],
        }
    }

    # Send based on preferences
    if prefs.push_enabled:
        await send_push_notification(user.id, content)

    if prefs.email_enabled:
        await send_email_notification(user.email, content)

    if prefs.sms_enabled and prefs.phone:
        await send_sms_notification(prefs.phone,
            f"Priority email from {match['match_client_name']}: {email_record.subject[:50]}")
```

---

## 7. Search & Filtering

### Filter Emails by Match Status

```python
# routes/email_routes.py

@router.get("/emails/search")
async def search_emails(
    matched: Optional[bool] = None,
    method: Optional[str] = None,
    min_confidence: Optional[float] = None,
    priority_only: bool = False,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search emails with identity resolution filters."""

    query = db.query(EmailReconciliationQueue).filter(
        EmailReconciliationQueue.user_id == current_user.id
    )

    if matched is True:
        query = query.filter(
            EmailReconciliationQueue.match_method.isnot(None)
        )
    elif matched is False:
        query = query.filter(
            EmailReconciliationQueue.match_method.is_(None)
        )

    if method:
        query = query.filter(
            EmailReconciliationQueue.match_method == method
        )

    if min_confidence:
        query = query.filter(
            EmailReconciliationQueue.match_confidence >= min_confidence
        )

    if priority_only:
        query = query.filter(
            EmailReconciliationQueue.is_priority == True
        )

    if loan_id:
        query = query.filter(
            EmailReconciliationQueue.matched_loan_id == loan_id
        )

    if lead_id:
        query = query.filter(
            EmailReconciliationQueue.matched_lead_id == lead_id
        )

    if contact_id:
        query = query.filter(
            EmailReconciliationQueue.matched_contact_id == contact_id
        )

    return query.order_by(
        EmailReconciliationQueue.received_date.desc()
    ).limit(100).all()
```

### Frontend Filter Component

```tsx
// components/EmailFilters.tsx

interface EmailFilters {
  matched?: boolean;
  method?: string;
  minConfidence?: number;
  priorityOnly?: boolean;
  loanId?: number;
}

export const EmailFilterPanel: React.FC<{
  filters: EmailFilters;
  onChange: (filters: EmailFilters) => void;
}> = ({ filters, onChange }) => {
  return (
    <div className="filter-panel">
      <Select
        label="Match Status"
        value={filters.matched}
        onChange={(v) => onChange({ ...filters, matched: v })}
        options={[
          { value: undefined, label: 'All' },
          { value: true, label: 'Matched' },
          { value: false, label: 'Unmatched' },
        ]}
      />

      <Select
        label="Match Method"
        value={filters.method}
        onChange={(v) => onChange({ ...filters, method: v })}
        options={[
          { value: '', label: 'Any Method' },
          { value: 'known_client_email', label: 'Known Client' },
          { value: 'lead_email_match', label: 'Lead' },
          { value: 'loan_email_match', label: 'Loan' },
          { value: 'domain_vendor_match', label: 'Vendor' },
        ]}
      />

      <Slider
        label="Min Confidence"
        min={0}
        max={100}
        value={(filters.minConfidence || 0) * 100}
        onChange={(v) => onChange({ ...filters, minConfidence: v / 100 })}
      />

      <Checkbox
        label="Priority Only"
        checked={filters.priorityOnly || false}
        onChange={(v) => onChange({ ...filters, priorityOnly: v })}
      />
    </div>
  );
};
```

---

## 8. Batch Operations

### Bulk Re-match Unmatched Emails

```python
# routes/email_intelligence_routes.py

@router.post("/email-intelligence/bulk-rematch")
async def bulk_rematch_emails(
    email_ids: List[int] = Body(None),
    rematch_all_unmatched: bool = Body(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Re-run identity resolution on selected emails."""

    resolver = get_email_identity_resolver(db)

    # Build query
    query = db.query(EmailReconciliationQueue).filter(
        EmailReconciliationQueue.user_id == current_user.id
    )

    if email_ids:
        query = query.filter(EmailReconciliationQueue.id.in_(email_ids))
    elif rematch_all_unmatched:
        query = query.filter(EmailReconciliationQueue.match_method.is_(None))
    else:
        raise HTTPException(400, "Must specify email_ids or rematch_all_unmatched")

    emails = query.all()
    results = {"total": len(emails), "updated": 0, "newly_matched": 0}

    for email in emails:
        email_data = {
            "from_email": email.from_email,
            "subject": email.subject,
            "thread_id": email.thread_id,
        }

        was_matched = email.match_method is not None
        match = resolver.resolve(email_data, current_user.id)

        # Update email record
        email.matched_contact_id = match["matched_contact_id"]
        email.matched_loan_id = match["matched_loan_id"]
        email.matched_lead_id = match["matched_lead_id"]
        email.match_method = match["match_method"]
        email.match_confidence = match["match_confidence"]
        email.match_evidence = match["match_evidence"]
        email.match_client_name = match["match_client_name"]
        email.match_loan_number = match["match_loan_number"]
        email.is_priority = match["is_priority"]

        results["updated"] += 1
        if not was_matched and match["match_method"]:
            results["newly_matched"] += 1

    db.commit()

    return results
```

---

## Next Steps

1. **Start with Basic Integration** - Add resolver to your email import endpoint
2. **Add Frontend Indicators** - Show match status in email list
3. **Enable Priority Routing** - Route high-priority emails for faster response
4. **Build Dashboard** - Monitor match rates and identify improvement areas
5. **Set Up Notifications** - Alert users to priority emails

For additional help, see:
- `README_EMAIL_IDENTITY.md` - Full technical documentation
- `SYSTEM_SUMMARY.md` - System overview
- `email_identity_usage_examples.py` - Code examples
