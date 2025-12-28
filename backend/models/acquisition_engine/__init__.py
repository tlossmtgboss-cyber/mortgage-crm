"""
Acquisition Engine Models
Campaign management, event tracking, and lead scoring for client acquisition
"""

from .campaign_models import CampaignBlueprint, CampaignInstance, GoalType, CampaignStatus
from .event_models import AcquisitionEvent, EventType
from .scoring_models import LeadTemperature, CampaignAttribution, Temperature

__all__ = [
    # Campaign models
    'CampaignBlueprint',
    'CampaignInstance',
    'GoalType',
    'CampaignStatus',
    # Event models
    'AcquisitionEvent',
    'EventType',
    # Scoring models
    'LeadTemperature',
    'CampaignAttribution',
    'Temperature',
]
