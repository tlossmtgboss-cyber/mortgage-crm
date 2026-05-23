"""
Workflow Confidence Scoring Service

Tracks AI confidence per (workflow_node × channel × organization).
Determines autonomy level: supervised (0-59), guided (60-84), autonomous (85-100).
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models.workflow_flowchart import WorkflowAIAction

logger = logging.getLogger(__name__)

AUTONOMY_THRESHOLDS = {
    "supervised": (0, 59),
    "guided": (60, 84),
    "autonomous": (85, 100),
}

CONFIDENCE_DELTAS = {
    "success": 4,
    "human_approved_no_edit": 2,
    "streak_bonus": 5,
    "human_rejected": -5,
    "human_edited": -3,
    "negative_outcome": -10,
    "compliance_violation": -100,
}


class WorkflowConfidenceService:
    def __init__(self, db: Session):
        self.db = db

    def get_confidence(self, node_id: str, channel: str) -> float:
        last_action = self.db.query(WorkflowAIAction).filter(
            WorkflowAIAction.workflow_node_id == node_id,
            WorkflowAIAction.channel == channel,
            WorkflowAIAction.confidence_after.isnot(None),
        ).order_by(WorkflowAIAction.created_at.desc()).first()

        if last_action:
            return last_action.confidence_after
        return 30.0

    def get_autonomy_level(self, node_id: str, channel: str) -> str:
        score = self.get_confidence(node_id, channel)
        for level, (low, high) in AUTONOMY_THRESHOLDS.items():
            if low <= score <= high:
                return level
        return "supervised"

    def get_all_channel_confidence(self, node_id: str) -> dict:
        channels = ["phone", "text", "email"]
        return {ch: {
            "score": self.get_confidence(node_id, ch),
            "level": self.get_autonomy_level(node_id, ch),
        } for ch in channels}

    def update_confidence(self, node_id: str, channel: str, event: str) -> float:
        current = self.get_confidence(node_id, channel)
        delta = CONFIDENCE_DELTAS.get(event, 0)

        if event == "compliance_violation":
            return 0.0

        if event == "success":
            recent = self.db.query(WorkflowAIAction).filter(
                WorkflowAIAction.workflow_node_id == node_id,
                WorkflowAIAction.channel == channel,
                WorkflowAIAction.outcome == "success",
            ).order_by(WorkflowAIAction.created_at.desc()).limit(10).count()
            if recent >= 10:
                delta += CONFIDENCE_DELTAS["streak_bonus"]

        new_score = max(0.0, min(100.0, current + delta))
        return new_score
