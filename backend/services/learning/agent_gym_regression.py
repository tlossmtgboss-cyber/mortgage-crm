"""
AgentGymRegression — Regression gate for agent harness updates (Domain 8).

No harness update ships without passing this gate.  Before a new agent
context version is promoted, we run the full synthetic test suite and
compare against prior-version scores across every regression dimension.

Usage:
    from services.learning.agent_gym_regression import agent_gym

    result = await agent_gym.run_regression(
        agent_id="document_tracker",
        new_version="v1.4",
        db=db,
    )
    if not result["passed"]:
        raise RuntimeError(f"Regression gate failed: {result['details']}")
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AgentGymRegression:
    """Regression gate.  No harness update ships without passing this."""

    SYNTHETIC_LOAN_FILES_MIN = 20

    REGRESSION_DIMENSIONS = [
        "condition_accuracy",
        "false_positive_rate",
        "response_completeness",
        "latency_p95",
        "guideline_citation_accuracy",
    ]

    # Maximum allowed regression per dimension (negative = improvement)
    # A dimension score can drop by at most this fraction before failing.
    REGRESSION_THRESHOLD = 0.05  # 5 %

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_regression(
        self,
        agent_id: str,
        new_version: str,
        db: Session,
    ) -> dict:
        """Run full regression suite against a new harness version.

        Returns:
            {
                "passed": bool,
                "agent_id": str,
                "version": str,
                "scores": {dimension: float, ...},
                "prior_scores": {dimension: float, ...},
                "details": [per-test result dicts],
                "run_id": str,
                "started_at": str,
                "finished_at": str,
            }
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        logger.info(
            "Regression run %s started for agent=%s version=%s",
            run_id,
            agent_id,
            new_version,
        )

        # 1. Load synthetic test suite
        test_suite = await self._load_test_suite(agent_id, db)
        if len(test_suite) < self.SYNTHETIC_LOAN_FILES_MIN:
            logger.warning(
                "Test suite for agent=%s has %d cases (min %d). "
                "Gate FAILS due to insufficient coverage.",
                agent_id,
                len(test_suite),
                self.SYNTHETIC_LOAN_FILES_MIN,
            )
            return {
                "passed": False,
                "agent_id": agent_id,
                "version": new_version,
                "scores": {},
                "prior_scores": {},
                "details": [],
                "error": (
                    f"Insufficient test cases: {len(test_suite)} "
                    f"< {self.SYNTHETIC_LOAN_FILES_MIN}"
                ),
                "run_id": run_id,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }

        # 2. Execute each test case against the new version
        results: list[dict] = []
        for test_case in test_suite:
            result = await self._run_single_test(
                agent_id, test_case, new_version, db,
            )
            results.append(result)

        # 3. Load prior version scores for comparison
        prior_scores = await self._load_prior_scores(agent_id, db)

        # 4. Evaluate regression across all dimensions
        evaluation = await self._evaluate_regression(results, prior_scores)

        finished_at = datetime.now(timezone.utc)
        passed = evaluation["passed"]

        # 5. Persist the run result
        await self._persist_run(
            run_id=run_id,
            agent_id=agent_id,
            version=new_version,
            passed=passed,
            scores=evaluation["scores"],
            prior_scores=prior_scores,
            started_at=started_at,
            finished_at=finished_at,
            db=db,
        )

        logger.info(
            "Regression run %s finished for agent=%s version=%s — %s",
            run_id,
            agent_id,
            new_version,
            "PASSED" if passed else "FAILED",
        )

        return {
            "passed": passed,
            "agent_id": agent_id,
            "version": new_version,
            "scores": evaluation["scores"],
            "prior_scores": prior_scores,
            "details": results,
            "regressions": evaluation.get("regressions", []),
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal — test suite loading
    # ------------------------------------------------------------------

    async def _load_test_suite(self, agent_id: str, db: Session) -> list:
        """Load synthetic test cases for the given agent.

        Test cases live in the ``agent_gym_test_cases`` table and include:
        - input payload (loan file snapshot)
        - expected output
        - dimension weights
        """
        try:
            result = db.execute(
                text(
                    "SELECT id, agent_id, test_name, input_payload, "
                    "       expected_output, dimension_weights "
                    "FROM agent_gym_test_cases "
                    "WHERE agent_id = :agent_id AND active = true "
                    "ORDER BY created_at"
                ),
                {"agent_id": agent_id},
            )
            rows = result.mappings().all()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(
                "Failed to load test suite for agent=%s: %s",
                agent_id,
                e,
            )
            return []

    # ------------------------------------------------------------------
    # Internal — single-test execution
    # ------------------------------------------------------------------

    async def _run_single_test(
        self,
        agent_id: str,
        test_case: dict,
        version: str,
        db: Session,
    ) -> dict:
        """Run a single test case and score across all dimensions.

        Returns a dict with per-dimension scores and latency.
        """
        start = time.perf_counter()

        try:
            # Invoke the agent with the test input payload.
            # In a full implementation this calls the agent service with the
            # specified version's harness/context.  For now we produce a
            # placeholder that the harness runner will fill in.
            agent_output = await self._invoke_agent(
                agent_id, test_case.get("input_payload", {}), version, db,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000

            # Score the output against expected
            scores = self._score_output(
                agent_output,
                test_case.get("expected_output", {}),
                test_case.get("dimension_weights", {}),
            )
            scores["latency_ms"] = round(elapsed_ms, 2)

            return {
                "test_id": test_case.get("id"),
                "test_name": test_case.get("test_name"),
                "passed": all(
                    scores.get(d, 1.0) >= 0.5 for d in self.REGRESSION_DIMENSIONS
                    if d != "latency_p95"
                ),
                "scores": scores,
                "error": None,
            }
        except Exception as e:
            logger.exception(
                "Test case %s failed for agent=%s: %s",
                test_case.get("id"),
                agent_id,
                e,
            )
            return {
                "test_id": test_case.get("id"),
                "test_name": test_case.get("test_name"),
                "passed": False,
                "scores": {d: 0.0 for d in self.REGRESSION_DIMENSIONS},
                "error": str(e),
            }

    async def _invoke_agent(
        self,
        agent_id: str,
        input_payload: dict,
        version: str,
        db: Session,
    ) -> dict:
        """Invoke the agent with a synthetic input payload.

        This is the integration point with the agent orchestration layer.
        The harness injects the versioned context before calling the agent.
        """
        # Deferred to agent orchestration integration — returns empty dict
        # until the harness runner is wired up.
        logger.debug(
            "invoke_agent stub called for agent=%s version=%s",
            agent_id,
            version,
        )
        return {}

    @staticmethod
    def _score_output(
        actual: dict,
        expected: dict,
        dimension_weights: dict,
    ) -> dict:
        """Score agent output against expected output per dimension.

        Simple field-level comparison for now; will be replaced with
        LLM-as-judge evaluation for nuanced dimensions (e.g.,
        guideline_citation_accuracy).
        """
        scores: dict[str, float] = {}

        if not expected:
            # No expected output — all dimensions default to 0 (untested)
            return {d: 0.0 for d in AgentGymRegression.REGRESSION_DIMENSIONS}

        # condition_accuracy — fraction of expected conditions present
        expected_conditions = expected.get("conditions", [])
        actual_conditions = actual.get("conditions", [])
        if expected_conditions:
            matches = sum(
                1 for ec in expected_conditions if ec in actual_conditions
            )
            scores["condition_accuracy"] = matches / len(expected_conditions)
        else:
            scores["condition_accuracy"] = 1.0

        # false_positive_rate — conditions in actual that are NOT expected
        if actual_conditions:
            false_positives = sum(
                1 for ac in actual_conditions if ac not in expected_conditions
            )
            scores["false_positive_rate"] = 1.0 - (
                false_positives / len(actual_conditions)
            )
        else:
            scores["false_positive_rate"] = 1.0

        # response_completeness — fraction of expected fields present
        expected_fields = set(expected.keys())
        actual_fields = set(actual.keys())
        if expected_fields:
            scores["response_completeness"] = (
                len(expected_fields & actual_fields) / len(expected_fields)
            )
        else:
            scores["response_completeness"] = 1.0

        # guideline_citation_accuracy — placeholder (LLM-as-judge later)
        expected_citations = expected.get("citations", [])
        actual_citations = actual.get("citations", [])
        if expected_citations:
            matches = sum(
                1 for ec in expected_citations if ec in actual_citations
            )
            scores["guideline_citation_accuracy"] = (
                matches / len(expected_citations)
            )
        else:
            scores["guideline_citation_accuracy"] = 1.0

        # latency_p95 is computed at aggregate level, not per-test
        scores["latency_p95"] = 0.0

        return scores

    # ------------------------------------------------------------------
    # Internal — regression evaluation
    # ------------------------------------------------------------------

    async def _evaluate_regression(
        self,
        results: list,
        prior_scores: dict,
    ) -> dict:
        """Compare aggregated scores against prior version.

        A dimension regresses if the new score drops more than
        ``REGRESSION_THRESHOLD`` below the prior score.
        """
        # Aggregate per-dimension scores across all test results
        aggregated: dict[str, list[float]] = {d: [] for d in self.REGRESSION_DIMENSIONS}

        latencies: list[float] = []
        for r in results:
            for d in self.REGRESSION_DIMENSIONS:
                if d == "latency_p95":
                    latency = r.get("scores", {}).get("latency_ms", 0.0)
                    if latency > 0:
                        latencies.append(latency)
                else:
                    val = r.get("scores", {}).get(d, 0.0)
                    aggregated[d].append(val)

        scores: dict[str, float] = {}
        for d in self.REGRESSION_DIMENSIONS:
            if d == "latency_p95":
                if latencies:
                    sorted_lat = sorted(latencies)
                    idx = int(len(sorted_lat) * 0.95)
                    scores[d] = round(sorted_lat[min(idx, len(sorted_lat) - 1)], 2)
                else:
                    scores[d] = 0.0
            else:
                vals = aggregated[d]
                scores[d] = round(sum(vals) / len(vals), 4) if vals else 0.0

        # Check for regressions
        regressions: list[dict] = []
        for d in self.REGRESSION_DIMENSIONS:
            prior = prior_scores.get(d)
            current = scores[d]

            if prior is None or prior == 0:
                continue  # No baseline — skip

            if d == "latency_p95":
                # For latency, regression means HIGHER latency
                if prior > 0 and current > prior * (1 + self.REGRESSION_THRESHOLD):
                    regressions.append({
                        "dimension": d,
                        "prior": prior,
                        "current": current,
                        "delta_pct": round(
                            ((current - prior) / prior) * 100, 2,
                        ),
                    })
            else:
                # For accuracy metrics, regression means LOWER score
                if current < prior * (1 - self.REGRESSION_THRESHOLD):
                    regressions.append({
                        "dimension": d,
                        "prior": prior,
                        "current": current,
                        "delta_pct": round(
                            ((current - prior) / prior) * 100, 2,
                        ),
                    })

        passed = len(regressions) == 0

        return {
            "passed": passed,
            "scores": scores,
            "regressions": regressions,
        }

    # ------------------------------------------------------------------
    # Internal — prior scores
    # ------------------------------------------------------------------

    async def _load_prior_scores(self, agent_id: str, db: Session) -> dict:
        """Load the most recent passing regression scores for comparison."""
        try:
            result = db.execute(
                text(
                    "SELECT scores FROM agent_gym_runs "
                    "WHERE agent_id = :agent_id AND passed = true "
                    "ORDER BY finished_at DESC LIMIT 1"
                ),
                {"agent_id": agent_id},
            )
            row = result.mappings().first()
            if row and row["scores"]:
                return dict(row["scores"])
        except Exception as e:
            logger.exception(
                "Failed to load prior scores for agent=%s: %s",
                agent_id,
                e,
            )

        return {}

    # ------------------------------------------------------------------
    # Internal — persist run results
    # ------------------------------------------------------------------

    async def _persist_run(
        self,
        *,
        run_id: str,
        agent_id: str,
        version: str,
        passed: bool,
        scores: dict,
        prior_scores: dict,
        started_at: datetime,
        finished_at: datetime,
        db: Session,
    ) -> None:
        """Write the regression run result to ``agent_gym_runs``."""
        try:
            import json

            db.execute(
                text(
                    "INSERT INTO agent_gym_runs "
                    "(id, agent_id, version, passed, scores, prior_scores, "
                    " started_at, finished_at) "
                    "VALUES (:id, :agent_id, :version, :passed, "
                    "        CAST(:scores AS jsonb), CAST(:prior_scores AS jsonb), "
                    "        :started_at, :finished_at)"
                ),
                {
                    "id": run_id,
                    "agent_id": agent_id,
                    "version": version,
                    "passed": passed,
                    "scores": json.dumps(scores, default=str),
                    "prior_scores": json.dumps(prior_scores, default=str),
                    "started_at": started_at,
                    "finished_at": finished_at,
                },
            )
            db.commit()
        except Exception as e:
            logger.exception(
                "Failed to persist gym run %s for agent=%s: %s",
                run_id,
                agent_id,
                e,
            )
            db.rollback()


# Singleton — importable by route handlers and jobs
agent_gym = AgentGymRegression()
