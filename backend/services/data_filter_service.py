"""
Data Filtering Service
Automatically applies territory/team/ownership filters to SQLAlchemy queries

Features:
- Territory-based filtering
- Team-based filtering
- Ownership-based filtering
- Automatic query modification
- Support for complex joins

Author: System
Date: 2025-11-15
"""

from typing import Optional, Dict, Any, Type
from sqlalchemy import and_, or_, Column
from sqlalchemy.orm import Query, Session
from sqlalchemy.ext.declarative import DeclarativeMeta


class DataFilterService:
    """
    Service for automatically filtering queries based on employee permissions

    Usage:
        filter_service = DataFilterService(db, permission_service)
        query = filter_service.apply_filters(
            query=db.query(Lead),
            employee_id=123,
            resource_type='lead'
        )
    """

    def __init__(self, db: Session, permission_service):
        """
        Initialize data filter service

        Args:
            db: SQLAlchemy database session
            permission_service: PermissionService instance
        """
        self.db = db
        self.permission_service = permission_service

    def apply_filters(
        self,
        query: Query,
        employee_id: int,
        resource_type: str,
        model: Optional[Type[DeclarativeMeta]] = None
    ) -> Query:
        """
        Apply data scope filters to a SQLAlchemy query

        Automatically filters based on employee's permissions:
        - view_all: No filters (returns all records)
        - view_team: Filters by team_id
        - view_territory: Filters by territory_id
        - view_assigned: Filters by assigned_to

        Args:
            query: SQLAlchemy query to filter
            employee_id: ID of the employee making the request
            resource_type: Type of resource ('lead', 'client', 'loan')
            model: SQLAlchemy model class (auto-detected if not provided)

        Returns:
            Filtered query

        Example:
            >>> query = db.query(Lead)
            >>> filtered = filter_service.apply_filters(query, 123, 'lead')
            >>> leads = filtered.all()  # Only returns leads user can see
        """

        # Get filter conditions from permission service
        filters = self.permission_service.get_data_scope_filter(
            employee_id,
            resource_type
        )

        # No filters = view_all permission
        if not filters:
            return query

        # Auto-detect model if not provided
        if model is None:
            model = self._get_model_from_query(query)

        # Apply filters to query
        conditions = []

        if 'team_id' in filters:
            conditions.append(model.team_id == filters['team_id'])

        if 'territory_id' in filters:
            conditions.append(model.territory_id == filters['territory_id'])

        if 'assigned_to' in filters:
            conditions.append(model.assigned_to == filters['assigned_to'])

        # Combine all conditions with AND
        if conditions:
            query = query.filter(and_(*conditions))

        return query

    def apply_multi_level_filters(
        self,
        query: Query,
        employee_id: int,
        resource_type: str,
        model: Optional[Type[DeclarativeMeta]] = None
    ) -> Query:
        """
        Apply multi-level filters with OR logic
        (team OR territory OR assigned - most permissive)

        Use this when employee should see data from multiple scopes

        Args:
            query: SQLAlchemy query to filter
            employee_id: ID of the employee making the request
            resource_type: Type of resource
            model: SQLAlchemy model class

        Returns:
            Filtered query with OR logic
        """

        permission_prefix = f"{resource_type}s"
        employee_info = self.permission_service._get_employee_info(employee_id)

        if not employee_info:
            # No access - return empty result
            return query.filter(False)

        # Auto-detect model if not provided
        if model is None:
            model = self._get_model_from_query(query)

        # Check view_all first
        if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_all"):
            return query  # No filters needed

        # Build OR conditions for multiple scopes
        conditions = []

        # Team-level access
        if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_team"):
            conditions.append(model.team_id == employee_info['team_id'])

        # Territory-level access
        if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_territory"):
            conditions.append(model.territory_id == employee_info['territory_id'])

        # Assigned access
        if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_assigned"):
            conditions.append(model.assigned_to == employee_id)

        # Apply OR filter
        if conditions:
            query = query.filter(or_(*conditions))
        else:
            # No permissions - return empty result
            query = query.filter(False)

        return query

    def filter_by_territory(
        self,
        query: Query,
        territory_id: int,
        model: Optional[Type[DeclarativeMeta]] = None
    ) -> Query:
        """
        Filter query by specific territory

        Args:
            query: SQLAlchemy query to filter
            territory_id: Territory ID to filter by
            model: SQLAlchemy model class

        Returns:
            Filtered query
        """

        if model is None:
            model = self._get_model_from_query(query)

        return query.filter(model.territory_id == territory_id)

    def filter_by_team(
        self,
        query: Query,
        team_id: int,
        model: Optional[Type[DeclarativeMeta]] = None
    ) -> Query:
        """
        Filter query by specific team

        Args:
            query: SQLAlchemy query to filter
            team_id: Team ID to filter by
            model: SQLAlchemy model class

        Returns:
            Filtered query
        """

        if model is None:
            model = self._get_model_from_query(query)

        return query.filter(model.team_id == team_id)

    def filter_by_owner(
        self,
        query: Query,
        employee_id: int,
        model: Optional[Type[DeclarativeMeta]] = None
    ) -> Query:
        """
        Filter query by assigned owner

        Args:
            query: SQLAlchemy query to filter
            employee_id: Employee ID who owns the records
            model: SQLAlchemy model class

        Returns:
            Filtered query
        """

        if model is None:
            model = self._get_model_from_query(query)

        return query.filter(model.assigned_to == employee_id)

    def can_access_record(
        self,
        employee_id: int,
        resource_type: str,
        record: Any,
        action: str = 'view'
    ) -> bool:
        """
        Check if employee can access a specific record

        Args:
            employee_id: ID of the employee
            resource_type: Type of resource
            record: The record object to check
            action: Action being performed ('view', 'edit', 'delete')

        Returns:
            True if employee can access the record
        """

        # Use permission service to check data scope
        return self.permission_service.check_data_scope(
            employee_id,
            resource_type,
            record.id,
            action
        )

    def get_accessible_territories(
        self,
        employee_id: int,
        resource_type: str
    ) -> list:
        """
        Get list of territory IDs that employee can access

        Args:
            employee_id: ID of the employee
            resource_type: Type of resource

        Returns:
            List of territory IDs
        """

        permission_prefix = f"{resource_type}s"

        # view_all = all territories
        if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_all"):
            # Return all territory IDs from database
            from sqlalchemy import text
            result = self.db.execute(text("SELECT id FROM territories"))
            return [row[0] for row in result]

        # view_territory = employee's territory only
        employee_info = self.permission_service._get_employee_info(employee_id)
        if employee_info and employee_info.get('territory_id'):
            if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_territory"):
                return [employee_info['territory_id']]

        return []

    def get_accessible_teams(
        self,
        employee_id: int,
        resource_type: str
    ) -> list:
        """
        Get list of team IDs that employee can access

        Args:
            employee_id: ID of the employee
            resource_type: Type of resource

        Returns:
            List of team IDs
        """

        permission_prefix = f"{resource_type}s"

        # view_all = all teams
        if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_all"):
            # Return all team IDs from database
            from sqlalchemy import text
            result = self.db.execute(text("SELECT id FROM teams"))
            return [row[0] for row in result]

        # view_team = employee's team only
        employee_info = self.permission_service._get_employee_info(employee_id)
        if employee_info and employee_info.get('team_id'):
            if self.permission_service.has_permission(employee_id, f"{permission_prefix}.view_team"):
                return [employee_info['team_id']]

        return []

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def _get_model_from_query(self, query: Query) -> Type[DeclarativeMeta]:
        """Extract model class from SQLAlchemy query"""

        # Try to get model from query column descriptions
        if hasattr(query, 'column_descriptions'):
            descriptions = query.column_descriptions
            if descriptions and len(descriptions) > 0:
                return descriptions[0]['type']

        # Fallback: try to get from query statement
        if hasattr(query, 'statement') and hasattr(query.statement, 'froms'):
            froms = list(query.statement.froms)
            if froms:
                return froms[0]

        raise ValueError("Could not determine model from query. Please provide model parameter.")


class QueryFilterMixin:
    """
    Mixin for SQLAlchemy models to add automatic filtering

    Usage:
        class Lead(Base, QueryFilterMixin):
            __tablename__ = 'leads'
            ...

        # In route handler:
        leads = Lead.query_for_employee(db, employee_id).all()
    """

    @classmethod
    def query_for_employee(
        cls,
        db: Session,
        employee_id: int,
        permission_service,
        resource_type: Optional[str] = None
    ) -> Query:
        """
        Get a filtered query for specific employee

        Args:
            db: Database session
            employee_id: Employee ID
            permission_service: PermissionService instance
            resource_type: Resource type (auto-detected from model if not provided)

        Returns:
            Filtered SQLAlchemy query
        """

        # Auto-detect resource type from table name
        if resource_type is None:
            table_name = cls.__tablename__
            # Remove 's' suffix (leads -> lead, clients -> client)
            resource_type = table_name.rstrip('s')

        # Create base query
        query = db.query(cls)

        # Apply filters
        filter_service = DataFilterService(db, permission_service)
        return filter_service.apply_filters(
            query,
            employee_id,
            resource_type,
            model=cls
        )

    @classmethod
    def get_accessible_by_employee(
        cls,
        db: Session,
        employee_id: int,
        permission_service,
        resource_type: Optional[str] = None
    ):
        """
        Get all records accessible by employee

        Args:
            db: Database session
            employee_id: Employee ID
            permission_service: PermissionService instance
            resource_type: Resource type

        Returns:
            List of records
        """

        query = cls.query_for_employee(db, employee_id, permission_service, resource_type)
        return query.all()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def apply_ownership_filter(
    query: Query,
    employee_id: int,
    ownership_column: str = 'assigned_to'
) -> Query:
    """
    Apply simple ownership filter to query

    Args:
        query: SQLAlchemy query
        employee_id: Employee ID
        ownership_column: Name of the ownership column

    Returns:
        Filtered query
    """

    return query.filter(getattr(query.column_descriptions[0]['type'], ownership_column) == employee_id)


def build_scope_conditions(
    model: Type[DeclarativeMeta],
    employee_info: Dict[str, Any],
    permissions: Dict[str, bool]
) -> list:
    """
    Build list of SQL conditions based on employee's scope

    Args:
        model: SQLAlchemy model class
        employee_info: Employee information (territory_id, team_id, etc.)
        permissions: Dictionary of permissions

    Returns:
        List of SQL conditions
    """

    conditions = []

    # Territory-based condition
    if employee_info.get('territory_id') and permissions.get('view_territory'):
        conditions.append(model.territory_id == employee_info['territory_id'])

    # Team-based condition
    if employee_info.get('team_id') and permissions.get('view_team'):
        conditions.append(model.team_id == employee_info['team_id'])

    # Ownership condition
    if permissions.get('view_assigned'):
        conditions.append(model.assigned_to == employee_info['employee_id'])

    return conditions
