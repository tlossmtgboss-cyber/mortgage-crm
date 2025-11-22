"""
Profitability Intelligence Service - Core calculation engine.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract
from models.profitability import (
    Expense, ExpenseCategory, EmployeeCost, ProfitabilityRole,
    ProfitabilityLoan, LoanAttribution, RevenueRecord,
    ProfitabilitySnapshot, ProfitabilityScenario, ProfitabilityInsight
)


class ProfitabilityService:
    """Core calculation engine for profitability analysis."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    # ============ Dashboard Metrics ============

    def get_dashboard_metrics(self, month: date) -> Dict[str, Any]:
        """Get complete dashboard metrics for a given month."""
        start_date = month.replace(day=1)
        if month.month == 12:
            end_date = date(month.year + 1, 1, 1)
        else:
            end_date = date(month.year, month.month + 1, 1)

        # Get revenue
        total_revenue = self._get_monthly_revenue(start_date, end_date)

        # Get expenses
        total_expenses = self._get_monthly_expenses(start_date, end_date)

        # Get loan counts
        loans_closed = self._get_loans_closed(start_date, end_date)

        # Calculate derived metrics
        net_profit = total_revenue - total_expenses
        profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal("0")
        cost_per_loan = total_expenses / loans_closed if loans_closed > 0 else Decimal("0")
        revenue_per_loan = total_revenue / loans_closed if loans_closed > 0 else Decimal("0")
        profit_per_loan = net_profit / loans_closed if loans_closed > 0 else Decimal("0")

        # Break-even analysis
        avg_revenue_per_loan = revenue_per_loan if revenue_per_loan > 0 else self._get_avg_revenue_per_loan()
        break_even_loans = int(total_expenses / avg_revenue_per_loan) if avg_revenue_per_loan > 0 else 0

        # Employee count
        employee_count = self._get_active_employee_count()

        return {
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "profit_margin": round(profit_margin, 2),
            "loans_closed": loans_closed,
            "cost_per_loan": round(cost_per_loan, 2),
            "revenue_per_loan": round(revenue_per_loan, 2),
            "profit_per_loan": round(profit_per_loan, 2),
            "break_even_loans": break_even_loans,
            "employee_count": employee_count,
            "month": month.strftime("%Y-%m")
        }

    def _get_monthly_revenue(self, start_date: date, end_date: date) -> Decimal:
        """Get total revenue for a month."""
        result = self.db.query(func.sum(RevenueRecord.amount)).filter(
            RevenueRecord.organization_id == self.organization_id,
            RevenueRecord.record_date >= start_date,
            RevenueRecord.record_date < end_date
        ).scalar()
        return Decimal(result or 0)

    def _get_monthly_expenses(self, start_date: date, end_date: date) -> Decimal:
        """Calculate total expenses for a month including employee costs."""
        # Fixed/recurring expenses
        expense_total = self.db.query(func.sum(Expense.amount)).filter(
            Expense.organization_id == self.organization_id,
            Expense.is_active == True,
            Expense.effective_date <= end_date,
            (Expense.end_date.is_(None)) | (Expense.end_date >= start_date)
        ).scalar() or Decimal(0)

        # Employee costs (monthly)
        employee_costs = self.db.query(
            func.sum(
                EmployeeCost.base_salary + EmployeeCost.benefits_cost +
                EmployeeCost.taxes_cost + EmployeeCost.equipment_cost +
                EmployeeCost.training_cost + EmployeeCost.other_costs
            ) / 12
        ).filter(
            EmployeeCost.organization_id == self.organization_id,
            EmployeeCost.is_active == True
        ).scalar() or Decimal(0)

        return Decimal(expense_total) + Decimal(employee_costs)

    def _get_loans_closed(self, start_date: date, end_date: date) -> int:
        """Get number of loans closed in a month."""
        return self.db.query(ProfitabilityLoan).filter(
            ProfitabilityLoan.organization_id == self.organization_id,
            ProfitabilityLoan.close_date >= start_date,
            ProfitabilityLoan.close_date < end_date
        ).count()

    def _get_avg_revenue_per_loan(self) -> Decimal:
        """Get average revenue per loan across all history."""
        result = self.db.query(func.avg(ProfitabilityLoan.total_revenue)).filter(
            ProfitabilityLoan.organization_id == self.organization_id
        ).scalar()
        return Decimal(result or 0)

    def _get_active_employee_count(self) -> int:
        """Get count of active employees."""
        return self.db.query(EmployeeCost).filter(
            EmployeeCost.organization_id == self.organization_id,
            EmployeeCost.is_active == True
        ).count()

    # ============ Role Profitability ============

    def get_role_profitability(self, month: date) -> List[Dict[str, Any]]:
        """Analyze profitability by role."""
        start_date = month.replace(day=1)
        if month.month == 12:
            end_date = date(month.year + 1, 1, 1)
        else:
            end_date = date(month.year, month.month + 1, 1)

        roles = self.db.query(ProfitabilityRole).filter(
            ProfitabilityRole.organization_id == self.organization_id,
            ProfitabilityRole.is_active == True
        ).all()

        results = []
        for role in roles:
            # Get employees in this role
            employees = self.db.query(EmployeeCost).filter(
                EmployeeCost.role_id == role.id,
                EmployeeCost.is_active == True
            ).all()

            employee_count = len(employees)
            total_cost = sum(emp.monthly_cost for emp in employees)

            # Get revenue attributed to this role
            employee_ids = [emp.id for emp in employees]
            if employee_ids:
                attributed_revenue = self.db.query(
                    func.sum(
                        ProfitabilityLoan.total_revenue * LoanAttribution.attribution_percentage / 100
                    )
                ).join(LoanAttribution).filter(
                    LoanAttribution.employee_cost_id.in_(employee_ids),
                    ProfitabilityLoan.close_date >= start_date,
                    ProfitabilityLoan.close_date < end_date
                ).scalar() or Decimal(0)

                loans_attributed = self.db.query(func.count(func.distinct(LoanAttribution.loan_id))).filter(
                    LoanAttribution.employee_cost_id.in_(employee_ids)
                ).join(ProfitabilityLoan).filter(
                    ProfitabilityLoan.close_date >= start_date,
                    ProfitabilityLoan.close_date < end_date
                ).scalar() or 0
            else:
                attributed_revenue = Decimal(0)
                loans_attributed = 0

            net_contribution = Decimal(attributed_revenue) - Decimal(total_cost)
            roi_percentage = (net_contribution / Decimal(total_cost) * 100) if total_cost > 0 else Decimal(0)
            cost_per_loan = Decimal(total_cost) / loans_attributed if loans_attributed > 0 else Decimal(0)

            results.append({
                "role_id": str(role.id),
                "role_name": role.name,
                "department": role.department,
                "employee_count": employee_count,
                "total_cost": round(Decimal(total_cost), 2),
                "total_revenue": round(Decimal(attributed_revenue), 2),
                "net_contribution": round(net_contribution, 2),
                "roi_percentage": round(roi_percentage, 2),
                "loans_attributed": loans_attributed,
                "cost_per_loan": round(cost_per_loan, 2),
                "is_profitable": net_contribution > 0
            })

        # Sort by net contribution descending
        results.sort(key=lambda x: x["net_contribution"], reverse=True)
        return results

    # ============ Employee Performance ============

    def get_employee_performance(self, month: date, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing employees by ROI."""
        start_date = month.replace(day=1)
        if month.month == 12:
            end_date = date(month.year + 1, 1, 1)
        else:
            end_date = date(month.year, month.month + 1, 1)

        employees = self.db.query(EmployeeCost).filter(
            EmployeeCost.organization_id == self.organization_id,
            EmployeeCost.is_active == True
        ).all()

        results = []
        for emp in employees:
            # Get attributed revenue and loans
            attributed_data = self.db.query(
                func.sum(
                    ProfitabilityLoan.total_revenue * LoanAttribution.attribution_percentage / 100
                ).label("revenue"),
                func.count(LoanAttribution.loan_id).label("loan_count"),
                func.avg(ProfitabilityLoan.loan_amount).label("avg_loan")
            ).join(ProfitabilityLoan).filter(
                LoanAttribution.employee_cost_id == emp.id,
                ProfitabilityLoan.close_date >= start_date,
                ProfitabilityLoan.close_date < end_date
            ).first()

            total_revenue = Decimal(attributed_data.revenue or 0)
            loans_closed = attributed_data.loan_count or 0
            avg_loan_size = Decimal(attributed_data.avg_loan or 0)

            monthly_cost = Decimal(emp.monthly_cost)
            net_contribution = total_revenue - monthly_cost
            roi_percentage = (net_contribution / monthly_cost * 100) if monthly_cost > 0 else Decimal(0)
            revenue_per_loan = total_revenue / loans_closed if loans_closed > 0 else Decimal(0)

            role_name = emp.role.name if emp.role else None

            results.append({
                "employee_id": str(emp.id),
                "employee_name": emp.employee_name,
                "role_name": role_name,
                "monthly_cost": round(monthly_cost, 2),
                "total_revenue": round(total_revenue, 2),
                "net_contribution": round(net_contribution, 2),
                "roi_percentage": round(roi_percentage, 2),
                "loans_closed": loans_closed,
                "avg_loan_size": round(avg_loan_size, 2),
                "revenue_per_loan": round(revenue_per_loan, 2)
            })

        # Sort by ROI and limit
        results.sort(key=lambda x: x["roi_percentage"], reverse=True)
        return results[:limit]

    # ============ Trend Analysis ============

    def get_trends(self, months: int = 12) -> List[Dict[str, Any]]:
        """Get historical trend data."""
        trends = []
        current_date = date.today().replace(day=1)

        for i in range(months):
            # Calculate month
            month_offset = current_date.month - i - 1
            year_offset = month_offset // 12
            month_num = month_offset % 12 + 1
            if month_num <= 0:
                month_num += 12
                year_offset -= 1
            month_date = date(current_date.year + year_offset, month_num, 1)

            metrics = self.get_dashboard_metrics(month_date)

            trends.append({
                "month": metrics["month"],
                "revenue": metrics["total_revenue"],
                "expenses": metrics["total_expenses"],
                "profit": metrics["net_profit"],
                "loans": metrics["loans_closed"],
                "cost_per_loan": metrics["cost_per_loan"]
            })

        trends.reverse()  # Oldest first
        return trends

    # ============ Gap & Gain Analysis ============

    def identify_gaps_and_gains(self, month: date) -> List[Dict[str, Any]]:
        """Identify gaps (problems) and gains (opportunities)."""
        items = []

        # Analyze role profitability for gaps/gains
        role_profitability = self.get_role_profitability(month)

        for role in role_profitability:
            if role["net_contribution"] < 0 and role["employee_count"] > 0:
                # Gap: Unprofitable role
                items.append({
                    "type": "gap",
                    "category": "Role Performance",
                    "title": f"{role['role_name']} is unprofitable",
                    "description": f"This role costs ${abs(role['net_contribution']):,.2f} more than it generates.",
                    "impact": abs(role["net_contribution"]),
                    "priority": "high" if abs(role["net_contribution"]) > 5000 else "medium",
                    "action": "Review staffing levels or revenue attribution"
                })
            elif role["roi_percentage"] > 50 and role["employee_count"] > 0:
                # Gain: High-performing role
                items.append({
                    "type": "gain",
                    "category": "Role Performance",
                    "title": f"{role['role_name']} has high ROI ({role['roi_percentage']:.0f}%)",
                    "description": f"Consider expanding this role to increase profitability.",
                    "impact": role["net_contribution"],
                    "priority": "medium",
                    "action": "Evaluate adding more staff to this role"
                })

        # Analyze metrics for additional insights
        metrics = self.get_dashboard_metrics(month)

        if metrics["profit_margin"] < 10:
            items.append({
                "type": "gap",
                "category": "Profitability",
                "title": f"Low profit margin ({metrics['profit_margin']:.1f}%)",
                "description": "Profit margin is below healthy threshold of 10%.",
                "impact": metrics["total_expenses"] * Decimal("0.1") - metrics["net_profit"],
                "priority": "high",
                "action": "Review expenses and pricing strategy"
            })

        if metrics["loans_closed"] < metrics["break_even_loans"]:
            gap = metrics["break_even_loans"] - metrics["loans_closed"]
            items.append({
                "type": "gap",
                "category": "Volume",
                "title": f"Below break-even ({gap} loans short)",
                "description": f"Need {metrics['break_even_loans']} loans to break even, only closed {metrics['loans_closed']}.",
                "impact": gap * metrics["revenue_per_loan"],
                "priority": "critical",
                "action": "Increase lead generation and conversion"
            })

        # Sort by priority and impact
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda x: (priority_order.get(x["priority"], 3), -float(x["impact"])))

        return items

    # ============ Scenario Modeling ============

    def run_scenario(self, base_month: date, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Run what-if scenario analysis."""
        # Get baseline metrics
        baseline = self.get_dashboard_metrics(base_month)

        # Apply scenario changes
        projected_revenue = baseline["total_revenue"]
        projected_expenses = baseline["total_expenses"]
        projected_loans = baseline["loans_closed"]

        # Loan volume changes
        if parameters.get("loan_volume_change"):
            change_pct = Decimal(str(parameters["loan_volume_change"])) / 100
            projected_loans = int(projected_loans * (1 + change_pct))
            projected_revenue = baseline["revenue_per_loan"] * projected_loans

        # Revenue per loan changes
        if parameters.get("revenue_per_loan_change"):
            change_pct = Decimal(str(parameters["revenue_per_loan_change"])) / 100
            projected_revenue = projected_revenue * (1 + change_pct)

        # Staff changes
        if parameters.get("staff_changes"):
            for role_id, change_count in parameters["staff_changes"].items():
                role = self.db.query(ProfitabilityRole).filter_by(id=role_id).first()
                if role:
                    avg_cost = (role.base_salary_range_min + role.base_salary_range_max) / 2 if role.base_salary_range_min and role.base_salary_range_max else Decimal("60000")
                    monthly_cost = avg_cost * (1 + role.typical_benefits_percentage / 100) / 12
                    projected_expenses += monthly_cost * change_count

        # Expense changes
        if parameters.get("expense_changes"):
            for category, pct_change in parameters["expense_changes"].items():
                change_pct = Decimal(str(pct_change)) / 100
                projected_expenses = projected_expenses * (1 + change_pct)

        # Calculate projected metrics
        projected_profit = projected_revenue - projected_expenses
        projected_margin = (projected_profit / projected_revenue * 100) if projected_revenue > 0 else Decimal(0)
        projected_cost_per_loan = projected_expenses / projected_loans if projected_loans > 0 else Decimal(0)
        projected_revenue_per_loan = projected_revenue / projected_loans if projected_loans > 0 else Decimal(0)
        projected_profit_per_loan = projected_profit / projected_loans if projected_loans > 0 else Decimal(0)
        projected_break_even = int(projected_expenses / projected_revenue_per_loan) if projected_revenue_per_loan > 0 else 0

        projected = {
            "total_revenue": round(projected_revenue, 2),
            "total_expenses": round(projected_expenses, 2),
            "net_profit": round(projected_profit, 2),
            "profit_margin": round(projected_margin, 2),
            "loans_closed": projected_loans,
            "cost_per_loan": round(projected_cost_per_loan, 2),
            "revenue_per_loan": round(projected_revenue_per_loan, 2),
            "profit_per_loan": round(projected_profit_per_loan, 2),
            "break_even_loans": projected_break_even,
            "employee_count": baseline["employee_count"] + sum(parameters.get("staff_changes", {}).values()),
            "month": base_month.strftime("%Y-%m")
        }

        # Generate recommendation
        profit_change = projected_profit - baseline["net_profit"]
        if profit_change > 0:
            recommendation = f"This scenario increases profit by ${profit_change:,.2f}. Consider implementing."
        elif profit_change < 0:
            recommendation = f"This scenario decreases profit by ${abs(profit_change):,.2f}. Review carefully."
        else:
            recommendation = "This scenario maintains current profitability."

        return {
            "baseline": baseline,
            "projected": projected,
            "revenue_change": round(projected_revenue - baseline["total_revenue"], 2),
            "expense_change": round(projected_expenses - baseline["total_expenses"], 2),
            "profit_change": round(profit_change, 2),
            "break_even_change": projected_break_even - baseline["break_even_loans"],
            "recommendation": recommendation
        }

    # ============ Snapshots ============

    def create_snapshot(self, month: date) -> ProfitabilitySnapshot:
        """Create or update monthly snapshot."""
        metrics = self.get_dashboard_metrics(month)

        # Check for existing snapshot
        existing = self.db.query(ProfitabilitySnapshot).filter(
            ProfitabilitySnapshot.organization_id == self.organization_id,
            ProfitabilitySnapshot.snapshot_month == month.replace(day=1)
        ).first()

        if existing:
            # Update existing
            existing.total_revenue = metrics["total_revenue"]
            existing.total_expenses = metrics["total_expenses"]
            existing.net_profit = metrics["net_profit"]
            existing.loans_closed = metrics["loans_closed"]
            existing.cost_per_loan = metrics["cost_per_loan"]
            existing.revenue_per_loan = metrics["revenue_per_loan"]
            existing.profit_per_loan = metrics["profit_per_loan"]
            existing.employee_count = metrics["employee_count"]
            existing.break_even_loans = metrics["break_even_loans"]
            existing.data_json = metrics
            snapshot = existing
        else:
            # Create new
            snapshot = ProfitabilitySnapshot(
                organization_id=self.organization_id,
                snapshot_month=month.replace(day=1),
                total_revenue=metrics["total_revenue"],
                total_expenses=metrics["total_expenses"],
                net_profit=metrics["net_profit"],
                loans_closed=metrics["loans_closed"],
                cost_per_loan=metrics["cost_per_loan"],
                revenue_per_loan=metrics["revenue_per_loan"],
                profit_per_loan=metrics["profit_per_loan"],
                employee_count=metrics["employee_count"],
                break_even_loans=metrics["break_even_loans"],
                data_json=metrics
            )
            self.db.add(snapshot)

        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    # ============ AI Insights ============

    def generate_insights(self, month: date) -> List[ProfitabilityInsight]:
        """Generate AI-powered insights for the month."""
        insights = []
        metrics = self.get_dashboard_metrics(month)
        gaps_gains = self.identify_gaps_and_gains(month)

        # Create insights from gaps and gains
        for item in gaps_gains[:5]:  # Top 5
            severity_map = {
                "critical": "critical",
                "high": "warning",
                "medium": "info",
                "low": "info"
            }
            insight_type = "gap" if item["type"] == "gap" else "gain"

            insight = ProfitabilityInsight(
                organization_id=self.organization_id,
                insight_type=insight_type,
                title=item["title"],
                description=item["description"],
                severity=severity_map.get(item["priority"], "info"),
                data_json={
                    "impact": float(item["impact"]),
                    "action": item["action"],
                    "category": item["category"]
                }
            )
            self.db.add(insight)
            insights.append(insight)

        self.db.commit()
        return insights
