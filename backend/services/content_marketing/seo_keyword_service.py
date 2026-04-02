"""
SEO Keyword Service

Handles SEO keyword research, tracking, and rankings:
- Keyword research and suggestions
- Ranking tracking over time
- Content-keyword association
- Mortgage industry keyword database
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
import httpx

from models.content_marketing import SEOKeyword, ContentBrief

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


class SEOKeywordService:
    """
    Service for SEO keyword management.

    Handles keyword research, tracking, and optimization
    for mortgage industry content.
    """

    # Mortgage industry seed keywords by category
    SEED_KEYWORDS = {
        "mortgage_basics": [
            "mortgage rates",
            "home loan",
            "mortgage calculator",
            "home mortgage",
            "mortgage lender",
            "mortgage broker",
        ],
        "loan_types": [
            "fha loan",
            "va loan",
            "conventional loan",
            "jumbo loan",
            "usda loan",
            "fha loan requirements",
            "va home loan",
        ],
        "refinance": [
            "refinance mortgage",
            "mortgage refinance rates",
            "cash out refinance",
            "refinance calculator",
            "when to refinance",
            "refinance closing costs",
        ],
        "first_time_buyer": [
            "first time home buyer",
            "first time home buyer programs",
            "down payment assistance",
            "first home buyer grants",
            "how to buy a house",
        ],
        "process": [
            "mortgage pre approval",
            "closing costs",
            "mortgage application",
            "mortgage underwriting",
            "mortgage approval",
            "mortgage closing",
        ],
        "credit": [
            "credit score for mortgage",
            "mortgage credit requirements",
            "improve credit score",
            "bad credit mortgage",
            "minimum credit score mortgage",
        ],
    }

    # Estimated search volumes (would come from API in production)
    DEFAULT_VOLUMES = {
        "mortgage rates": 450000,
        "home loan": 110000,
        "fha loan": 90500,
        "va loan": 74000,
        "refinance mortgage": 60500,
        "first time home buyer": 49500,
        "mortgage calculator": 301000,
        "mortgage pre approval": 33100,
    }

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.llm_enabled = bool(ANTHROPIC_API_KEY)

    # =========================================================================
    # Keyword CRUD
    # =========================================================================

    def add_keyword(
        self,
        keyword: str,
        user_id: Optional[int] = None,
        organization_id: int = 1,
        category: Optional[str] = None,
        search_volume: Optional[int] = None,
        difficulty_score: Optional[float] = None,
        target_ranking: int = 10,
        priority: int = 3,
    ) -> Dict[str, Any]:
        """Add a keyword to track."""
        try:
            # Check if keyword already exists
            existing = self.db.query(SEOKeyword).filter(
                SEOKeyword.keyword == keyword.lower(),
                SEOKeyword.organization_id == organization_id
            ).first()

            if existing:
                return {
                    "success": False,
                    "error": "Keyword already exists",
                    "keyword_id": existing.id
                }

            # Estimate volume if not provided
            if search_volume is None:
                search_volume = self.DEFAULT_VOLUMES.get(keyword.lower(), 1000)

            seo_keyword = SEOKeyword(
                user_id=user_id,
                organization_id=organization_id,
                keyword=keyword.lower(),
                search_volume=search_volume,
                difficulty_score=difficulty_score or self._estimate_difficulty(keyword),
                target_ranking=target_ranking,
                category=category or self._categorize_keyword(keyword),
                intent=self._determine_intent(keyword),
                status="active",
                priority=priority,
                ranking_history=[],
                content_brief_ids=[],
                content_item_ids=[],
            )

            self.db.add(seo_keyword)
            self.db.commit()
            self.db.refresh(seo_keyword)

            return {
                "success": True,
                "keyword_id": seo_keyword.id,
                "keyword": seo_keyword.keyword,
                "category": seo_keyword.category,
                "search_volume": seo_keyword.search_volume,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to add keyword: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_keyword(self, keyword_id: str) -> Optional[SEOKeyword]:
        """Get a keyword by ID."""
        return self.db.query(SEOKeyword).filter(
            SEOKeyword.id == keyword_id
        ).first()

    def get_keyword_by_text(
        self,
        keyword: str,
        organization_id: int = 1
    ) -> Optional[SEOKeyword]:
        """Get a keyword by its text."""
        return self.db.query(SEOKeyword).filter(
            SEOKeyword.keyword == keyword.lower(),
            SEOKeyword.organization_id == organization_id
        ).first()

    def list_keywords(
        self,
        organization_id: int = 1,
        category: Optional[str] = None,
        status: Optional[str] = None,
        min_volume: Optional[int] = None,
        max_difficulty: Optional[float] = None,
        sort_by: str = "priority",
    ) -> List[SEOKeyword]:
        """List keywords with filters."""
        query = self.db.query(SEOKeyword).filter(
            SEOKeyword.organization_id == organization_id
        )

        if category:
            query = query.filter(SEOKeyword.category == category)
        if status:
            query = query.filter(SEOKeyword.status == status)
        if min_volume:
            query = query.filter(SEOKeyword.search_volume >= min_volume)
        if max_difficulty:
            query = query.filter(SEOKeyword.difficulty_score <= max_difficulty)

        # Sorting
        if sort_by == "priority":
            query = query.order_by(SEOKeyword.priority, SEOKeyword.search_volume.desc())
        elif sort_by == "volume":
            query = query.order_by(SEOKeyword.search_volume.desc())
        elif sort_by == "difficulty":
            query = query.order_by(SEOKeyword.difficulty_score)
        elif sort_by == "ranking":
            query = query.order_by(SEOKeyword.current_ranking.nullslast())

        return query.all()

    def update_keyword(
        self,
        keyword_id: str,
        updates: Dict[str, Any]
    ) -> Optional[SEOKeyword]:
        """Update a keyword."""
        keyword = self.get_keyword(keyword_id)
        if not keyword:
            return None

        allowed_fields = [
            "target_ranking", "priority", "category", "status",
            "search_volume", "difficulty_score"
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(keyword, field, value)

        self.db.commit()
        self.db.refresh(keyword)
        return keyword

    def delete_keyword(self, keyword_id: str) -> bool:
        """Archive a keyword."""
        keyword = self.get_keyword(keyword_id)
        if not keyword:
            return False

        keyword.status = "archived"
        self.db.commit()
        return True

    # =========================================================================
    # Ranking Tracking
    # =========================================================================

    def update_ranking(
        self,
        keyword_id: str,
        ranking: int,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update the ranking for a keyword."""
        keyword = self.get_keyword(keyword_id)
        if not keyword:
            return {"success": False, "error": "Keyword not found"}

        previous_ranking = keyword.current_ranking

        # Update current ranking
        keyword.current_ranking = ranking
        keyword.last_checked_at = datetime.now(timezone.utc)

        # Update best ranking
        if keyword.best_ranking is None or ranking < keyword.best_ranking:
            keyword.best_ranking = ranking

        # Add to history
        history = keyword.ranking_history or []
        history.append({
            "date": date.today().isoformat(),
            "ranking": ranking,
            "url": url,
        })
        # Keep last 90 days
        keyword.ranking_history = history[-90:]

        # Check if target achieved
        if ranking <= keyword.target_ranking and keyword.status != "achieved":
            keyword.status = "achieved"

        self.db.commit()

        return {
            "success": True,
            "keyword_id": keyword_id,
            "keyword": keyword.keyword,
            "previous_ranking": previous_ranking,
            "current_ranking": ranking,
            "change": (previous_ranking - ranking) if previous_ranking else None,
            "target_achieved": ranking <= keyword.target_ranking,
        }

    def bulk_update_rankings(
        self,
        rankings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk update rankings for multiple keywords."""
        results = []
        for item in rankings:
            keyword_text = item.get("keyword")
            ranking = item.get("ranking")

            if keyword_text and ranking:
                keyword = self.get_keyword_by_text(keyword_text)
                if keyword:
                    result = self.update_ranking(keyword.id, ranking, item.get("url"))
                    results.append(result)

        return {
            "success": True,
            "updated_count": len(results),
            "results": results,
        }

    def get_ranking_history(
        self,
        keyword_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get ranking history for a keyword."""
        keyword = self.get_keyword(keyword_id)
        if not keyword or not keyword.ranking_history:
            return []

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return [
            entry for entry in keyword.ranking_history
            if entry.get("date", "") >= cutoff
        ]

    def get_ranking_changes(
        self,
        organization_id: int = 1,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get ranking changes over a period."""
        keywords = self.list_keywords(organization_id=organization_id, status="active")

        improvements = []
        declines = []
        no_change = []

        for keyword in keywords:
            history = keyword.ranking_history or []
            if len(history) < 2:
                continue

            # Compare current to N days ago
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            old_rankings = [h for h in history if h.get("date", "") <= cutoff]
            recent_rankings = [h for h in history if h.get("date", "") > cutoff]

            if old_rankings and recent_rankings:
                old_rank = old_rankings[-1].get("ranking", 100)
                new_rank = recent_rankings[-1].get("ranking", 100)
                change = old_rank - new_rank  # Positive = improvement

                entry = {
                    "keyword": keyword.keyword,
                    "keyword_id": keyword.id,
                    "old_ranking": old_rank,
                    "new_ranking": new_rank,
                    "change": change,
                }

                if change > 0:
                    improvements.append(entry)
                elif change < 0:
                    declines.append(entry)
                else:
                    no_change.append(entry)

        return {
            "period_days": days,
            "improvements": sorted(improvements, key=lambda x: x["change"], reverse=True),
            "declines": sorted(declines, key=lambda x: x["change"]),
            "no_change": no_change,
            "summary": {
                "improved_count": len(improvements),
                "declined_count": len(declines),
                "stable_count": len(no_change),
            }
        }

    # =========================================================================
    # Keyword Research
    # =========================================================================

    async def suggest_keywords(
        self,
        seed_keyword: str,
        category: Optional[str] = None,
        count: int = 10
    ) -> List[Dict[str, Any]]:
        """Suggest related keywords based on a seed keyword."""
        suggestions = []

        # Get from seed database first
        for cat, keywords in self.SEED_KEYWORDS.items():
            if category and cat != category:
                continue

            for kw in keywords:
                if seed_keyword.lower() in kw.lower() or kw.lower() in seed_keyword.lower():
                    suggestions.append({
                        "keyword": kw,
                        "category": cat,
                        "search_volume": self.DEFAULT_VOLUMES.get(kw, 1000),
                        "difficulty": self._estimate_difficulty(kw),
                        "source": "seed_database",
                    })

        # Use LLM to generate additional suggestions
        if self.llm_enabled and len(suggestions) < count:
            llm_suggestions = await self._generate_keyword_suggestions(
                seed_keyword, count - len(suggestions)
            )
            suggestions.extend(llm_suggestions)

        return suggestions[:count]

    async def _generate_keyword_suggestions(
        self,
        seed_keyword: str,
        count: int
    ) -> List[Dict[str, Any]]:
        """Generate keyword suggestions using LLM."""
        try:
            prompt = f"""Generate {count} SEO keyword suggestions related to "{seed_keyword}" for the mortgage/home loan industry.

For each keyword, provide:
1. The keyword phrase (2-5 words)
2. Estimated monthly search volume (be realistic)
3. Difficulty score (0-100)
4. Search intent (informational, transactional, navigational)

Respond with JSON:
{{
    "suggestions": [
        {{
            "keyword": "keyword phrase",
            "search_volume": 5000,
            "difficulty": 45,
            "intent": "informational"
        }}
    ]
}}

Focus on keywords that would be valuable for mortgage professionals to rank for."""

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

                if response.status_code == 200:
                    import json
                    result = response.json()
                    text = result["content"][0]["text"]

                    # Parse JSON from response
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0]

                    data = json.loads(text.strip())
                    suggestions = data.get("suggestions", [])

                    # Add source marker
                    for s in suggestions:
                        s["source"] = "ai_generated"
                        s["category"] = self._categorize_keyword(s.get("keyword", ""))

                    return suggestions

        except Exception as e:
            logger.error(f"Error generating keyword suggestions: {e}")

        return []

    def get_keyword_opportunities(
        self,
        organization_id: int = 1
    ) -> Dict[str, Any]:
        """Identify keyword opportunities based on current rankings."""
        keywords = self.list_keywords(organization_id=organization_id, status="active")

        # Quick wins (ranking 11-20, could reach page 1)
        quick_wins = [
            k for k in keywords
            if k.current_ranking and 11 <= k.current_ranking <= 20
        ]

        # Striking distance (ranking 4-10, could reach top 3)
        striking_distance = [
            k for k in keywords
            if k.current_ranking and 4 <= k.current_ranking <= 10
        ]

        # High volume low competition
        high_value = [
            k for k in keywords
            if k.search_volume and k.search_volume > 5000
            and k.difficulty_score and k.difficulty_score < 40
        ]

        # Declining keywords (need attention)
        declining = []
        for k in keywords:
            history = k.ranking_history or []
            if len(history) >= 2:
                recent = history[-1].get("ranking", 100)
                previous = history[-2].get("ranking", 100)
                if recent > previous + 5:  # Dropped more than 5 positions
                    declining.append(k)

        return {
            "quick_wins": [
                {"keyword": k.keyword, "ranking": k.current_ranking, "volume": k.search_volume}
                for k in sorted(quick_wins, key=lambda x: x.search_volume or 0, reverse=True)[:10]
            ],
            "striking_distance": [
                {"keyword": k.keyword, "ranking": k.current_ranking, "volume": k.search_volume}
                for k in sorted(striking_distance, key=lambda x: x.search_volume or 0, reverse=True)[:10]
            ],
            "high_value_opportunities": [
                {"keyword": k.keyword, "volume": k.search_volume, "difficulty": k.difficulty_score}
                for k in high_value[:10]
            ],
            "declining_keywords": [
                {"keyword": k.keyword, "current_ranking": k.current_ranking}
                for k in declining[:10]
            ],
        }

    # =========================================================================
    # Content Association
    # =========================================================================

    def associate_keyword_with_brief(
        self,
        keyword_id: str,
        brief_id: str
    ) -> bool:
        """Associate a keyword with a content brief."""
        keyword = self.get_keyword(keyword_id)
        if not keyword:
            return False

        brief_ids = keyword.content_brief_ids or []
        if brief_id not in brief_ids:
            brief_ids.append(brief_id)
            keyword.content_brief_ids = brief_ids
            self.db.commit()

        return True

    def get_briefs_for_keyword(
        self,
        keyword_id: str
    ) -> List[ContentBrief]:
        """Get all briefs associated with a keyword."""
        keyword = self.get_keyword(keyword_id)
        if not keyword or not keyword.content_brief_ids:
            return []

        return self.db.query(ContentBrief).filter(
            ContentBrief.id.in_(keyword.content_brief_ids)
        ).all()

    def get_keywords_for_brief(
        self,
        brief_id: str
    ) -> List[SEOKeyword]:
        """Get all keywords associated with a brief."""
        # Check primary keyword on brief
        brief = self.db.query(ContentBrief).filter(
            ContentBrief.id == brief_id
        ).first()

        if not brief:
            return []

        keywords = []

        # Get primary keyword
        if brief.primary_keyword:
            primary = self.get_keyword_by_text(brief.primary_keyword, brief.organization_id)
            if primary:
                keywords.append(primary)

        # Get keywords that reference this brief
        associated = self.db.query(SEOKeyword).filter(
            SEOKeyword.content_brief_ids.contains([brief_id])
        ).all()

        for kw in associated:
            if kw not in keywords:
                keywords.append(kw)

        return keywords

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_keyword_analytics(
        self,
        organization_id: int = 1
    ) -> Dict[str, Any]:
        """Get overall keyword analytics."""
        keywords = self.list_keywords(organization_id=organization_id)

        total = len(keywords)
        active = len([k for k in keywords if k.status == "active"])
        achieved = len([k for k in keywords if k.status == "achieved"])
        page_one = len([k for k in keywords if k.current_ranking and k.current_ranking <= 10])
        top_three = len([k for k in keywords if k.current_ranking and k.current_ranking <= 3])

        total_volume = sum(k.search_volume or 0 for k in keywords if k.current_ranking and k.current_ranking <= 10)

        by_category = {}
        for k in keywords:
            cat = k.category or "uncategorized"
            if cat not in by_category:
                by_category[cat] = {"count": 0, "page_one": 0, "volume": 0}
            by_category[cat]["count"] += 1
            if k.current_ranking and k.current_ranking <= 10:
                by_category[cat]["page_one"] += 1
                by_category[cat]["volume"] += k.search_volume or 0

        return {
            "total_keywords": total,
            "active_keywords": active,
            "achieved_targets": achieved,
            "page_one_rankings": page_one,
            "top_three_rankings": top_three,
            "total_search_volume": total_volume,
            "by_category": by_category,
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _estimate_difficulty(self, keyword: str) -> float:
        """Estimate keyword difficulty (simplified)."""
        # In production, this would use actual SEO API data
        word_count = len(keyword.split())

        # Longer tail keywords are generally easier
        if word_count >= 4:
            return 25.0
        elif word_count == 3:
            return 40.0
        elif word_count == 2:
            return 55.0
        else:
            return 70.0

    def _categorize_keyword(self, keyword: str) -> str:
        """Categorize a keyword based on content."""
        keyword_lower = keyword.lower()

        category_patterns = {
            "refinance": ["refinance", "refi"],
            "first_time_buyer": ["first time", "first-time", "new buyer"],
            "loan_types": ["fha", "va", "conventional", "jumbo", "usda"],
            "credit": ["credit score", "credit requirement"],
            "process": ["pre-approval", "preapproval", "closing", "underwriting", "application"],
            "rates": ["rate", "apr", "interest"],
        }

        for category, patterns in category_patterns.items():
            for pattern in patterns:
                if pattern in keyword_lower:
                    return category

        return "mortgage_basics"

    def _determine_intent(self, keyword: str) -> str:
        """Determine search intent for a keyword."""
        keyword_lower = keyword.lower()

        # Transactional intent
        transactional = ["buy", "apply", "get", "find", "best", "compare", "rates near"]
        if any(t in keyword_lower for t in transactional):
            return "transactional"

        # Navigational intent
        navigational = ["login", "account", "contact", "phone number", "near me"]
        if any(n in keyword_lower for n in navigational):
            return "navigational"

        # Default to informational
        return "informational"

    # =========================================================================
    # Seed Data
    # =========================================================================

    def seed_mortgage_keywords(
        self,
        user_id: Optional[int] = None,
        organization_id: int = 1
    ) -> Dict[str, Any]:
        """Seed the database with mortgage industry keywords."""
        created = 0
        skipped = 0

        for category, keywords in self.SEED_KEYWORDS.items():
            for keyword in keywords:
                result = self.add_keyword(
                    keyword=keyword,
                    user_id=user_id,
                    organization_id=organization_id,
                    category=category,
                    priority=2 if category in ["mortgage_basics", "loan_types"] else 3,
                )
                if result.get("success"):
                    created += 1
                else:
                    skipped += 1

        return {
            "success": True,
            "created": created,
            "skipped": skipped,
            "categories": list(self.SEED_KEYWORDS.keys()),
        }
