"""
Agent Gym Service
Provides business logic for agent training and simulation:
- Training scenario management
- Training session execution and evaluation
- Agent skill assessment
- Performance benchmarking
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, Integer
import json
import uuid
import random

from models.agent_governance import (
    AgentProfile, AgentExecution,
    TrainingScenario, TrainingSession
)


class AgentGymService:
    """Service for agent training and simulation operations."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # TRAINING SCENARIO MANAGEMENT
    # =========================================================================

    def create_training_scenario(
        self,
        name: str,
        description: str,
        agent_type: str,
        difficulty: str,
        scenario_data: Dict[str, Any],
        expected_outcomes: Dict[str, Any],
        category: str = "general",
        time_limit_seconds: Optional[int] = None,
        max_score: int = 100
    ) -> TrainingScenario:
        """Create a new training scenario."""
        scenario = TrainingScenario(
            name=name,
            description=description,
            category=category,
            target_agent_type=agent_type,
            difficulty=difficulty,
            input_data=scenario_data,
            expected_output=expected_outcomes,
            time_limit_seconds=time_limit_seconds,
            max_score=max_score,
            is_active=True
        )

        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(scenario)

        return scenario

    def get_scenario(self, scenario_id) -> Optional[TrainingScenario]:
        """Get a training scenario by ID."""
        try:
            scenario_id_int = int(scenario_id) if isinstance(scenario_id, str) else scenario_id
        except (ValueError, TypeError):
            return None
        return self.db.query(TrainingScenario).filter(
            TrainingScenario.id == scenario_id_int
        ).first()

    def list_scenarios(
        self,
        agent_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        category: Optional[str] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List training scenarios with filtering."""
        query = self.db.query(TrainingScenario)

        if is_active is not None:
            query = query.filter(TrainingScenario.is_active == is_active)

        if agent_type:
            query = query.filter(TrainingScenario.target_agent_type == agent_type)

        if difficulty:
            query = query.filter(TrainingScenario.difficulty == difficulty)

        if category:
            query = query.filter(TrainingScenario.category == category)

        total = query.count()
        scenarios = query.order_by(TrainingScenario.created_at.desc()).offset(offset).limit(limit).all()

        return {
            "scenarios": scenarios,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    def update_scenario(
        self,
        scenario_id,
        updates: Dict[str, Any]
    ) -> Optional[TrainingScenario]:
        """Update a training scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return None

        # Map API field names to model field names
        field_mapping = {
            'scenario_data': 'input_data',
            'expected_outcomes': 'expected_output',
            'agent_type': 'target_agent_type',
        }

        allowed_fields = [
            'name', 'description', 'difficulty', 'category', 'target_agent_type',
            'input_data', 'expected_output', 'time_limit_seconds', 'max_score', 'is_active'
        ]

        for field, value in updates.items():
            # Map field name if needed
            mapped_field = field_mapping.get(field, field)
            if mapped_field in allowed_fields:
                setattr(scenario, mapped_field, value)

        self.db.commit()
        self.db.refresh(scenario)

        return scenario

    def delete_scenario(self, scenario_id: str) -> bool:
        """Soft delete a training scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return False

        scenario.is_active = False
        scenario.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        return True

    def get_scenario_stats(self, scenario_id: str) -> Dict[str, Any]:
        """Get statistics for a training scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return {}

        sessions = self.db.query(TrainingSession).filter(
            TrainingSession.scenario_id == scenario_id
        ).all()

        if not sessions:
            return {
                "scenario_id": scenario_id,
                "total_sessions": 0,
                "completed_sessions": 0,
                "average_score": None,
                "pass_rate": None,
                "average_duration_seconds": None
            }

        completed = [s for s in sessions if s.status == 'completed']
        passed = [s for s in completed if s.passed]

        scores = [s.score for s in completed if s.score is not None]
        durations = [s.duration_seconds for s in completed if s.duration_seconds]

        return {
            "scenario_id": scenario_id,
            "total_sessions": len(sessions),
            "completed_sessions": len(completed),
            "average_score": sum(scores) / len(scores) if scores else None,
            "pass_rate": len(passed) / len(completed) * 100 if completed else None,
            "average_duration_seconds": sum(durations) / len(durations) if durations else None,
            "by_agent": self._get_scenario_stats_by_agent(scenario_id)
        }

    def _get_scenario_stats_by_agent(self, scenario_id: str) -> List[Dict[str, Any]]:
        """Get scenario stats broken down by agent."""
        results = self.db.query(
            TrainingSession.agent_id,
            func.count(TrainingSession.id).label('attempts'),
            func.avg(TrainingSession.score).label('avg_score'),
            func.sum(func.cast(TrainingSession.passed, Integer)).label('passes')
        ).filter(
            TrainingSession.scenario_id == scenario_id,
            TrainingSession.status == 'completed'
        ).group_by(TrainingSession.agent_id).all()

        stats = []
        for r in results:
            agent = self.db.query(AgentProfile).filter(AgentProfile.id == r.agent_id).first()
            stats.append({
                "agent_id": r.agent_id,
                "agent_name": (agent.display_name or agent.agent_name) if agent else "Unknown",
                "attempts": r.attempts,
                "average_score": float(r.avg_score) if r.avg_score else None,
                "passes": r.passes or 0,
                "pass_rate": (r.passes / r.attempts * 100) if r.attempts > 0 else 0
            })

        return stats

    # =========================================================================
    # TRAINING SESSION MANAGEMENT
    # =========================================================================

    def start_training_session(
        self,
        agent_id: str,
        scenario_id: str,
        initiated_by: Optional[str] = None
    ) -> TrainingSession:
        """Start a new training session."""
        agent = self.db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")

        if not scenario.is_active:
            raise ValueError(f"Scenario {scenario_id} is not active")

        session = TrainingSession(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            scenario_id=scenario_id,
            status='in_progress',
            started_at=datetime.now(timezone.utc),
            initiated_by=initiated_by
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return session

    def get_training_session(self, session_id: str) -> Optional[TrainingSession]:
        """Get a training session by ID."""
        return self.db.query(TrainingSession).filter(
            TrainingSession.id == session_id
        ).first()

    def complete_training_session(
        self,
        session_id: str,
        results: Dict[str, Any],
        score: float,
        passed: bool,
        feedback: Optional[str] = None
    ) -> TrainingSession:
        """Complete a training session with results."""
        session = self.get_training_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.status != 'in_progress':
            raise ValueError(f"Session {session_id} is not in progress")

        session.completed_at = datetime.now(timezone.utc)
        session.status = 'completed'
        session.results = results
        session.score = score
        session.passed = passed
        session.feedback = feedback

        # Calculate duration
        if session.started_at:
            duration = (session.completed_at - session.started_at).total_seconds()
            session.duration_seconds = int(duration)

        self.db.commit()
        self.db.refresh(session)

        # Update agent training stats
        self._update_agent_training_stats(session.agent_id)

        return session

    def fail_training_session(
        self,
        session_id: str,
        error: str
    ) -> TrainingSession:
        """Mark a training session as failed."""
        session = self.get_training_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.completed_at = datetime.now(timezone.utc)
        session.status = 'failed'
        session.results = {"error": error}
        session.passed = False

        if session.started_at:
            duration = (session.completed_at - session.started_at).total_seconds()
            session.duration_seconds = int(duration)

        self.db.commit()
        self.db.refresh(session)

        return session

    def list_training_sessions(
        self,
        agent_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        status: Optional[str] = None,
        days: int = 30,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List training sessions with filtering."""
        query = self.db.query(TrainingSession)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(TrainingSession.started_at >= cutoff)

        if agent_id:
            query = query.filter(TrainingSession.agent_id == agent_id)

        if scenario_id:
            query = query.filter(TrainingSession.scenario_id == scenario_id)

        if status:
            query = query.filter(TrainingSession.status == status)

        total = query.count()
        sessions = query.order_by(TrainingSession.started_at.desc()).offset(offset).limit(limit).all()

        return {
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    def _update_agent_training_stats(self, agent_id: str):
        """Update agent's training statistics after completing a session."""
        agent = self.db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            return

        # Get all completed training sessions for this agent
        sessions = self.db.query(TrainingSession).filter(
            TrainingSession.agent_id == agent_id,
            TrainingSession.status == 'completed'
        ).all()

        if not sessions:
            return

        passed = [s for s in sessions if s.passed]
        scores = [s.score for s in sessions if s.score is not None]

        # Update capabilities with training stats
        if not agent.capabilities:
            agent.capabilities = {}

        agent.capabilities['training_stats'] = {
            "total_sessions": len(sessions),
            "passed_sessions": len(passed),
            "pass_rate": len(passed) / len(sessions) * 100 if sessions else 0,
            "average_score": sum(scores) / len(scores) if scores else None,
            "last_training": datetime.now(timezone.utc).isoformat()
        }

        self.db.commit()

    # =========================================================================
    # AGENT SKILL ASSESSMENT
    # =========================================================================

    def assess_agent_skills(self, agent_id: str) -> Dict[str, Any]:
        """Assess an agent's skills based on training and execution history."""
        agent = self.db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            return {}

        # Get training performance
        training_sessions = self.db.query(TrainingSession).filter(
            TrainingSession.agent_id == agent_id,
            TrainingSession.status == 'completed'
        ).all()

        # Get execution performance
        executions = self.db.query(AgentExecution).filter(
            AgentExecution.agent_id == agent_id,
            AgentExecution.status == 'completed'
        ).order_by(AgentExecution.created_at.desc()).limit(100).all()

        # Calculate skill scores by difficulty
        difficulty_scores = self._calculate_difficulty_scores(training_sessions)

        # Calculate tool proficiency
        tool_proficiency = self._calculate_tool_proficiency(executions)

        # Calculate response quality metrics
        quality_metrics = self._calculate_quality_metrics(executions)

        # Calculate overall skill level
        overall_score = self._calculate_overall_skill_score(
            difficulty_scores, tool_proficiency, quality_metrics
        )

        return {
            "agent_id": agent_id,
            "agent_name": agent.display_name or agent.agent_name,
            "overall_skill_score": overall_score,
            "skill_level": self._score_to_level(overall_score),
            "difficulty_scores": difficulty_scores,
            "tool_proficiency": tool_proficiency,
            "quality_metrics": quality_metrics,
            "training_summary": {
                "total_sessions": len(training_sessions),
                "passed": len([s for s in training_sessions if s.passed]),
                "scenarios_completed": len(set(s.scenario_id for s in training_sessions))
            },
            "execution_summary": {
                "total_executions": len(executions),
                "successful": len([e for e in executions if e.success])
            },
            "assessed_at": datetime.now(timezone.utc).isoformat()
        }

    def _calculate_difficulty_scores(
        self,
        sessions: List[TrainingSession]
    ) -> Dict[str, Any]:
        """Calculate performance scores by difficulty level."""
        by_difficulty = {}

        for session in sessions:
            scenario = self.get_scenario(session.scenario_id)
            if not scenario:
                continue

            difficulty = scenario.difficulty
            if difficulty not in by_difficulty:
                by_difficulty[difficulty] = {"attempts": 0, "passed": 0, "scores": []}

            by_difficulty[difficulty]["attempts"] += 1
            if session.passed:
                by_difficulty[difficulty]["passed"] += 1
            if session.score is not None:
                by_difficulty[difficulty]["scores"].append(session.score)

        result = {}
        for difficulty, data in by_difficulty.items():
            result[difficulty] = {
                "attempts": data["attempts"],
                "pass_rate": data["passed"] / data["attempts"] * 100 if data["attempts"] > 0 else 0,
                "average_score": sum(data["scores"]) / len(data["scores"]) if data["scores"] else None
            }

        return result

    def _calculate_tool_proficiency(
        self,
        executions: List[AgentExecution]
    ) -> Dict[str, Any]:
        """Calculate proficiency with different tools."""
        tool_stats = {}

        for execution in executions:
            if not execution.tools_used:
                continue

            for tool in execution.tools_used:
                if tool not in tool_stats:
                    tool_stats[tool] = {"uses": 0, "successful_uses": 0}

                tool_stats[tool]["uses"] += 1
                if execution.success:
                    tool_stats[tool]["successful_uses"] += 1

        result = {}
        for tool, stats in tool_stats.items():
            success_rate = stats["successful_uses"] / stats["uses"] * 100 if stats["uses"] > 0 else 0
            result[tool] = {
                "uses": stats["uses"],
                "success_rate": success_rate,
                "proficiency_level": self._rate_to_proficiency(success_rate)
            }

        return result

    def _calculate_quality_metrics(
        self,
        executions: List[AgentExecution]
    ) -> Dict[str, Any]:
        """Calculate quality metrics from executions."""
        if not executions:
            return {
                "average_response_time": None,
                "success_rate": None,
                "error_rate": None
            }

        response_times = [e.execution_time_ms for e in executions if e.execution_time_ms]
        successful = len([e for e in executions if e.success])
        errors = len([e for e in executions if e.error_message])

        return {
            "average_response_time_ms": sum(response_times) / len(response_times) if response_times else None,
            "success_rate": successful / len(executions) * 100 if executions else None,
            "error_rate": errors / len(executions) * 100 if executions else None,
            "total_evaluated": len(executions)
        }

    def _calculate_overall_skill_score(
        self,
        difficulty_scores: Dict[str, Any],
        tool_proficiency: Dict[str, Any],
        quality_metrics: Dict[str, Any]
    ) -> float:
        """Calculate overall skill score from component scores."""
        scores = []
        weights = []

        # Weight difficulty scores
        difficulty_weights = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
        for difficulty, data in difficulty_scores.items():
            if data.get("average_score") is not None:
                weight = difficulty_weights.get(difficulty, 1)
                scores.append(data["average_score"] * weight)
                weights.append(weight)

        # Add tool proficiency score
        if tool_proficiency:
            tool_rates = [v.get("success_rate", 0) for v in tool_proficiency.values()]
            if tool_rates:
                scores.append(sum(tool_rates) / len(tool_rates))
                weights.append(2)

        # Add quality metrics
        if quality_metrics.get("success_rate") is not None:
            scores.append(quality_metrics["success_rate"])
            weights.append(2)

        if not scores:
            return 0.0

        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)

    def _score_to_level(self, score: float) -> str:
        """Convert numeric score to skill level."""
        if score >= 90:
            return "Expert"
        elif score >= 75:
            return "Advanced"
        elif score >= 60:
            return "Intermediate"
        elif score >= 40:
            return "Beginner"
        else:
            return "Novice"

    def _rate_to_proficiency(self, rate: float) -> str:
        """Convert success rate to proficiency level."""
        if rate >= 95:
            return "Master"
        elif rate >= 85:
            return "Proficient"
        elif rate >= 70:
            return "Competent"
        elif rate >= 50:
            return "Learning"
        else:
            return "Novice"

    # =========================================================================
    # BENCHMARKING
    # =========================================================================

    def benchmark_agent(
        self,
        agent_id: str,
        scenario_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Run benchmark tests on an agent."""
        agent = self.db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            return {}

        # Get scenarios to benchmark
        if scenario_ids:
            # Convert string IDs to integers
            int_ids = [int(sid) if isinstance(sid, str) else sid for sid in scenario_ids]
            scenarios = self.db.query(TrainingScenario).filter(
                TrainingScenario.id.in_(int_ids),
                TrainingScenario.is_active == True
            ).all()
        else:
            # Get standard benchmark scenarios for agent's category
            scenarios = self.db.query(TrainingScenario).filter(
                TrainingScenario.target_agent_type == agent.category,
                TrainingScenario.is_active == True
            ).all()

        if not scenarios:
            return {
                "agent_id": agent_id,
                "error": "No benchmark scenarios available"
            }

        benchmark_id = str(uuid.uuid4())[:8]
        results = []

        for scenario in scenarios:
            # Get agent's best performance on this scenario
            best_session = self.db.query(TrainingSession).filter(
                TrainingSession.agent_id == agent_id,
                TrainingSession.scenario_id == scenario.id,
                TrainingSession.status == 'completed'
            ).order_by(TrainingSession.score.desc()).first()

            # Get average performance across all agents
            avg_score = self.db.query(func.avg(TrainingSession.score)).filter(
                TrainingSession.scenario_id == scenario.id,
                TrainingSession.status == 'completed'
            ).scalar()

            results.append({
                "scenario_id": scenario.id,
                "scenario_name": scenario.name,
                "difficulty": scenario.difficulty,
                "agent_best_score": best_session.score if best_session else None,
                "agent_passed": best_session.passed if best_session else None,
                "average_score": float(avg_score) if avg_score else None,
                "percentile": self._calculate_percentile(
                    agent_id, scenario.id, best_session.score if best_session else None
                )
            })

        # Calculate overall benchmark score
        agent_scores = [r["agent_best_score"] for r in results if r["agent_best_score"] is not None]
        overall_score = sum(agent_scores) / len(agent_scores) if agent_scores else None

        return {
            "benchmark_id": benchmark_id,
            "agent_id": agent_id,
            "agent_name": agent.display_name or agent.agent_name,
            "overall_score": overall_score,
            "scenarios_tested": len(scenarios),
            "scenarios_completed": len(agent_scores),
            "results": results,
            "benchmarked_at": datetime.now(timezone.utc).isoformat()
        }

    def _calculate_percentile(
        self,
        agent_id: str,
        scenario_id: str,
        score: Optional[float]
    ) -> Optional[float]:
        """Calculate agent's percentile for a scenario."""
        if score is None:
            return None

        # Count how many agents scored lower
        lower_count = self.db.query(
            func.count(func.distinct(TrainingSession.agent_id))
        ).filter(
            TrainingSession.scenario_id == scenario_id,
            TrainingSession.status == 'completed',
            TrainingSession.score < score
        ).scalar()

        # Count total agents
        total_count = self.db.query(
            func.count(func.distinct(TrainingSession.agent_id))
        ).filter(
            TrainingSession.scenario_id == scenario_id,
            TrainingSession.status == 'completed'
        ).scalar()

        if total_count == 0:
            return None

        return (lower_count / total_count) * 100

    def get_leaderboard(
        self,
        agent_type: Optional[str] = None,
        scenario_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get training leaderboard."""
        query = self.db.query(
            TrainingSession.agent_id,
            func.avg(TrainingSession.score).label('avg_score'),
            func.count(TrainingSession.id).label('sessions'),
            func.sum(func.cast(TrainingSession.passed, Integer)).label('passed')
        ).filter(
            TrainingSession.status == 'completed'
        )

        if scenario_id:
            query = query.filter(TrainingSession.scenario_id == scenario_id)

        query = query.group_by(TrainingSession.agent_id)
        query = query.order_by(func.avg(TrainingSession.score).desc())
        query = query.limit(limit)

        results = query.all()

        leaderboard = []
        for rank, r in enumerate(results, 1):
            agent = self.db.query(AgentProfile).filter(AgentProfile.id == r.agent_id).first()

            # Filter by agent type/category if specified
            if agent_type and agent and agent.category != agent_type:
                continue

            leaderboard.append({
                "rank": rank,
                "agent_id": r.agent_id,
                "agent_name": (agent.display_name or agent.agent_name) if agent else "Unknown",
                "agent_type": agent.category if agent else None,
                "average_score": float(r.avg_score) if r.avg_score else 0,
                "sessions": r.sessions,
                "passed": r.passed or 0,
                "pass_rate": (r.passed / r.sessions * 100) if r.sessions > 0 else 0
            })

        return leaderboard

    # =========================================================================
    # SCENARIO GENERATION
    # =========================================================================

    def generate_scenario_from_execution(
        self,
        execution_id: str,
        difficulty: str = "intermediate"
    ) -> Optional[TrainingScenario]:
        """Generate a training scenario from a real execution."""
        execution = self.db.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            return None

        agent = self.db.query(AgentProfile).filter(
            AgentProfile.id == execution.agent_id
        ).first()

        # Create scenario data from execution
        scenario_data = {
            "input": execution.input_data,
            "context": execution.context or {},
            "tools_available": execution.tools_used or [],
            "source_execution_id": execution_id
        }

        # Define expected outcomes based on actual execution
        expected_outcomes = {
            "success": execution.success,
            "expected_tools": execution.tools_used,
            "reference_output": execution.output_data if execution.success else None
        }

        scenario = self.create_training_scenario(
            name=f"Generated: {execution.action_type or 'Task'} Scenario",
            description=f"Auto-generated scenario from execution {execution_id}",
            agent_type=agent.category if agent else "general",
            difficulty=difficulty,
            scenario_data=scenario_data,
            expected_outcomes=expected_outcomes,
            category="auto-generated"
        )

        return scenario

    def get_recommended_scenarios(
        self,
        agent_id: str,
        limit: int = 5
    ) -> List[TrainingScenario]:
        """Get recommended training scenarios for an agent."""
        agent = self.db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            return []

        # Get scenarios the agent hasn't completed
        completed_ids = self.db.query(TrainingSession.scenario_id).filter(
            TrainingSession.agent_id == agent_id,
            TrainingSession.status == 'completed',
            TrainingSession.passed == True
        ).distinct().subquery()

        # Get scenarios agent hasn't passed
        query = self.db.query(TrainingScenario).filter(
            TrainingScenario.target_agent_type == agent.category,
            TrainingScenario.is_active == True,
            ~TrainingScenario.id.in_(completed_ids)
        )

        # Prioritize by difficulty progression
        assessment = self.assess_agent_skills(agent_id)
        skill_level = assessment.get("skill_level", "Novice")

        # Map skill level to recommended difficulty
        difficulty_map = {
            "Novice": ["beginner"],
            "Beginner": ["beginner", "intermediate"],
            "Intermediate": ["intermediate", "advanced"],
            "Advanced": ["advanced", "expert"],
            "Expert": ["expert"]
        }

        recommended_difficulties = difficulty_map.get(skill_level, ["beginner"])

        scenarios = query.filter(
            TrainingScenario.difficulty.in_(recommended_difficulties)
        ).limit(limit).all()

        # If not enough, add from other difficulties
        if len(scenarios) < limit:
            additional = query.filter(
                ~TrainingScenario.difficulty.in_(recommended_difficulties)
            ).limit(limit - len(scenarios)).all()
            scenarios.extend(additional)

        return scenarios
