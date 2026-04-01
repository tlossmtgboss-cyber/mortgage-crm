"""Per-tenant script customization service — manage AI persona, qualifying questions, and behavior config."""
import logging
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Default qualifying questions bank
DEFAULT_QUESTION_BANK = [
    {"id": "loan_type", "question": "What type of loan are you looking for?", "options": ["Purchase", "Refinance", "HELOC", "Other"], "required": True, "order": 1},
    {"id": "loan_amount", "question": "What is the approximate purchase price or loan amount?", "required": True, "order": 2},
    {"id": "property_state", "question": "What state is the property in?", "required": True, "order": 3},
    {"id": "credit_range", "question": "What is your estimated credit score range?", "options": ["760+", "720-759", "680-719", "640-679", "Below 640"], "required": True, "order": 4},
    {"id": "employment_type", "question": "Are you currently employed, self-employed, or retired?", "options": ["W-2 Employed", "Self-Employed", "1099 Contractor", "Retired"], "required": True, "order": 5},
    {"id": "timeline", "question": "What is your target timeline?", "options": ["ASAP", "1-3 months", "3-6 months", "Just exploring"], "required": True, "order": 6},
    {"id": "down_payment", "question": "Do you have a down payment saved?", "options": ["Yes, 20%+", "Yes, 10-19%", "Yes, 3-9%", "No / Not sure"], "required": False, "order": 7},
    {"id": "first_time_buyer", "question": "Is this your first home purchase?", "options": ["Yes", "No"], "required": False, "order": 8},
    {"id": "veteran_status", "question": "Have you or your spouse served in the military?", "options": ["Yes", "No"], "required": False, "order": 9},
    {"id": "current_rate", "question": "What is your current mortgage rate?", "required": False, "order": 10, "show_for": ["Refinance"]},
]

# Default transfer threshold
DEFAULT_TRANSFER_THRESHOLD = {
    "min_credit_score": 680,
    "max_timeline": "3 months",
    "loan_types": ["Purchase", "Refinance"],
    "require_employment": True,
}

DEFAULT_PERSONA = {
    "name": "Aria",
    "voice": "deepgram/asteria",
    "personality": "professional, warm, knowledgeable",
    "greeting_style": "friendly",
}


class ScriptCustomizationService:
    """Manages per-tenant AI script configuration."""

    def get_config(self, db: Session, organization_id: str) -> Dict:
        """Get full script customization config for an organization."""
        try:
            row = db.execute(text("""
                SELECT config_data FROM organization_ai_configs
                WHERE organization_id = :org_id
                LIMIT 1
            """), {"org_id": organization_id}).mappings().first()

            if row and row["config_data"]:
                import json
                return json.loads(row["config_data"]) if isinstance(row["config_data"], str) else row["config_data"]
        except Exception:
            logger.debug("organization_ai_configs table not available, using defaults")

        return self._default_config(organization_id)

    def save_config(self, db: Session, organization_id: str, config: Dict) -> Dict:
        """Save script customization config for an organization."""
        import json
        config_json = json.dumps(config)

        try:
            # Upsert
            db.execute(text("""
                INSERT INTO organization_ai_configs (organization_id, config_data, updated_at)
                VALUES (:org_id, :config::json, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id)
                DO UPDATE SET config_data = :config::json, updated_at = CURRENT_TIMESTAMP
            """), {"org_id": organization_id, "config": config_json})
            db.commit()
            return {"status": "saved", "organization_id": organization_id}
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to save config: {e}")
            return {"status": "error", "detail": str(e)}

    def update_persona(self, db: Session, organization_id: str, persona: Dict) -> Dict:
        """Update AI persona settings."""
        config = self.get_config(db, organization_id)
        config["persona"] = {**config.get("persona", {}), **persona}
        return self.save_config(db, organization_id, config)

    def update_questions(self, db: Session, organization_id: str, questions: List[Dict]) -> Dict:
        """Update qualifying questions list."""
        config = self.get_config(db, organization_id)
        config["qualifying_questions"] = questions
        return self.save_config(db, organization_id, config)

    def update_transfer_threshold(self, db: Session, organization_id: str, threshold: Dict) -> Dict:
        """Update transfer/qualification threshold."""
        config = self.get_config(db, organization_id)
        config["transfer_threshold"] = {**config.get("transfer_threshold", {}), **threshold}
        return self.save_config(db, organization_id, config)

    def update_quiet_hours(self, db: Session, organization_id: str, quiet_hours: Dict) -> Dict:
        """Update quiet hours configuration."""
        config = self.get_config(db, organization_id)
        config["quiet_hours"] = {**config.get("quiet_hours", {}), **quiet_hours}
        return self.save_config(db, organization_id, config)

    def update_drip_settings(self, db: Session, organization_id: str, drip_settings: Dict) -> Dict:
        """Update drip sequence enablement."""
        config = self.get_config(db, organization_id)
        config["drip_settings"] = {**config.get("drip_settings", {}), **drip_settings}
        return self.save_config(db, organization_id, config)

    def get_question_bank(self) -> List[Dict]:
        """Get the master question bank."""
        return DEFAULT_QUESTION_BANK

    def _default_config(self, organization_id: str) -> Dict:
        return {
            "organization_id": organization_id,
            "persona": DEFAULT_PERSONA.copy(),
            "qualifying_questions": DEFAULT_QUESTION_BANK.copy(),
            "transfer_threshold": DEFAULT_TRANSFER_THRESHOLD.copy(),
            "quiet_hours": {
                "start": "21:00",
                "end": "08:00",
                "timezone": "America/New_York",
                "weekend_calls": False,
            },
            "drip_settings": {
                "purchase_12_month": True,
                "refinance_12_month": True,
                "post_close": True,
                "reengagement": True,
            },
            "voicemail_scripts": {},
            "suppression_list_count": 0,
        }


_service = None


def get_script_customization_service() -> ScriptCustomizationService:
    global _service
    if _service is None:
        _service = ScriptCustomizationService()
    return _service
