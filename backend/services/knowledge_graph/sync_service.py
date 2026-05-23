"""
KnowledgeGraphSyncService — populates the graph from existing CRM entities.

Reads leads, loans, users, referral partners, loan team members, and MUM
clients, then upserts corresponding nodes and edges. Idempotent — safe to
re-run. Each sync method can run independently for incremental updates.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .graph_service import KnowledgeGraphService

logger = logging.getLogger(__name__)


class KnowledgeGraphSyncService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.graph = KnowledgeGraphService(db, organization_id)
        self._stats: dict[str, int] = {"nodes_upserted": 0, "edges_upserted": 0}

    # =====================================================================
    # Full sync
    # =====================================================================

    def sync_all(self, since: datetime | None = None) -> dict[str, Any]:
        """
        Full entity sync. If `since` is provided, only entities updated after
        that timestamp are synced (incremental).
        """
        self._stats = {"nodes_upserted": 0, "edges_upserted": 0}

        self._sync_users(since)
        self._sync_referral_partners(since)
        self._sync_leads(since)
        self._sync_loans(since)
        self._sync_loan_team_members(since)
        self._sync_mum_clients(since)
        self._cleanup_stale_edges()
        self._cleanup_deleted_nodes()

        self.db.flush()
        stats = self.graph.get_stats()
        stats["sync"] = self._stats
        return stats

    # =====================================================================
    # Per-entity sync methods
    # =====================================================================

    def _sync_users(self, since: datetime | None = None) -> None:
        from database.models.core import User

        q = self.db.query(User).filter(
            User.organization_id == self.organization_id,
            User.is_active == True,
        )

        users = q.all()

        # Pass 1: upsert all user nodes so manager references resolve
        user_nodes: dict[int, Any] = {}
        for user in users:
            label = _user_label(user)
            props = {
                "email": user.email,
                "role": user.role,
                "permission_role": user.permission_role,
                "nmls_number": user.nmls_number,
                "slug": user.slug,
            }
            node = self.graph.upsert_node("user", str(user.id), label, _clean(props))
            user_nodes[user.id] = node
            self._stats["nodes_upserted"] += 1

        # Pass 2: create edges (manager nodes now guaranteed to exist)
        for user in users:
            node = user_nodes[user.id]

            if user.manager_id:
                mgr_node = user_nodes.get(user.manager_id) or self.graph.get_node("user", str(user.manager_id))
                if mgr_node:
                    self.graph.upsert_edge(mgr_node.id, node.id, "manages")
                    self._stats["edges_upserted"] += 1

            if user.branch_id:
                branch_node = self._ensure_branch_node(user.branch_id)
                if branch_node:
                    self.graph.upsert_edge(node.id, branch_node.id, "in_branch")
                    self._stats["edges_upserted"] += 1

    def _sync_leads(self, since: datetime | None = None) -> None:
        from database.models.lead_loan import Lead

        q = self.db.query(Lead).filter(
            Lead.organization_id == self.organization_id,
            Lead.deleted_at == None,
        )
        if since:
            q = q.filter(Lead.updated_at >= since)

        for lead in q.all():
            label = lead.name or f"Lead #{lead.id}"
            props = {
                "email": lead.email,
                "phone": lead.phone,
                "stage": lead.stage,
                "source": lead.source,
                "ai_score": lead.ai_score,
                "loan_type": lead.loan_type,
                "loan_number": lead.loan_number,
            }
            node = self.graph.upsert_node("lead", str(lead.id), label, _clean(props))
            self._stats["nodes_upserted"] += 1

            if lead.owner_id:
                owner_node = self.graph.get_node("user", str(lead.owner_id))
                if owner_node:
                    self.graph.upsert_edge(owner_node.id, node.id, "owns_lead")
                    self._stats["edges_upserted"] += 1

            if lead.referral_partner_id:
                rp_node = self.graph.get_node("referral_partner", str(lead.referral_partner_id))
                if rp_node:
                    self.graph.upsert_edge(rp_node.id, node.id, "referred")
                    self._stats["edges_upserted"] += 1

            if lead.co_applicant_email:
                co_label = lead.co_applicant_name or "Co-Applicant"
                co_node = self.graph.upsert_node(
                    "contact", f"co_{lead.id}", co_label,
                    _clean({"email": lead.co_applicant_email, "role": "co_applicant"}),
                )
                self.graph.upsert_edge(node.id, co_node.id, "co_applicant")
                self._stats["nodes_upserted"] += 1
                self._stats["edges_upserted"] += 1

    def _sync_loans(self, since: datetime | None = None) -> None:
        from database.models.lead_loan import Lead, Loan

        q = self.db.query(Loan).filter(
            Loan.organization_id == self.organization_id,
            Loan.deleted_at == None,
        )
        if since:
            q = q.filter(Loan.updated_at >= since)

        loans = q.all()

        loan_numbers = [l.loan_number for l in loans if l.loan_number]
        lead_by_loan_number: dict[str, int] = {}
        if loan_numbers:
            leads_with_ln = (
                self.db.query(Lead.loan_number, Lead.id)
                .filter(
                    Lead.organization_id == self.organization_id,
                    Lead.loan_number.in_(loan_numbers),
                    Lead.deleted_at == None,
                )
                .all()
            )
            lead_by_loan_number = {ln: lid for ln, lid in leads_with_ln}

        for loan in loans:
            label = _loan_label(loan)
            props = {
                "loan_number": loan.loan_number,
                "stage": loan.stage,
                "amount": str(loan.amount) if loan.amount else None,
                "loan_type": loan.loan_type,
                "rate": str(loan.rate) if loan.rate else None,
                "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                "funded_date": loan.funded_date.isoformat() if loan.funded_date else None,
            }
            node = self.graph.upsert_node("loan", str(loan.id), label, _clean(props))
            self._stats["nodes_upserted"] += 1

            if loan.loan_officer_id:
                lo_node = self.graph.get_node("user", str(loan.loan_officer_id))
                if lo_node:
                    self.graph.upsert_edge(lo_node.id, node.id, "officers_loan")
                    self._stats["edges_upserted"] += 1

            if loan.loan_number:
                lead_id = lead_by_loan_number.get(loan.loan_number)
                if lead_id:
                    lead_node = self.graph.get_node("lead", str(lead_id))
                    if lead_node:
                        self.graph.upsert_edge(lead_node.id, node.id, "has_loan")
                        self._stats["edges_upserted"] += 1

    def _sync_referral_partners(self, since: datetime | None = None) -> None:
        from database.models.referral import ReferralPartner

        q = self.db.query(ReferralPartner).filter(
            ReferralPartner.organization_id == self.organization_id,
        )
        if since and hasattr(ReferralPartner, "updated_at"):
            q = q.filter(ReferralPartner.updated_at >= since)
        elif since:
            q = q.filter(ReferralPartner.created_at >= since)

        for rp in q.all():
            label = rp.name or rp.business_name or f"Partner #{rp.id}"
            props = {
                "company": rp.company or rp.business_name,
                "category": rp.category,
                "email": rp.email,
                "phone": rp.phone,
                "status": rp.status,
                "loyalty_tier": rp.loyalty_tier,
                "referrals_in": rp.referrals_in,
                "closed_loans": rp.closed_loans,
                "volume": str(rp.volume) if rp.volume else None,
            }
            node = self.graph.upsert_node("referral_partner", str(rp.id), label, _clean(props))
            self._stats["nodes_upserted"] += 1

            if rp.owner_id:
                owner_node = self.graph.get_node("user", str(rp.owner_id))
                if owner_node:
                    self.graph.upsert_edge(owner_node.id, node.id, "works_with", weight=_rp_weight(rp))
                    self._stats["edges_upserted"] += 1

    def _sync_loan_team_members(self, since: datetime | None = None) -> None:
        from database.models.referral import LoanTeamMember
        from database.models.lead_loan import Loan
        from database.models.knowledge_graph import KnowledgeGraphNode

        q = (
            self.db.query(LoanTeamMember)
            .join(Loan, LoanTeamMember.loan_id == Loan.id)
            .filter(Loan.organization_id == self.organization_id)
        )
        if since:
            q = q.filter(LoanTeamMember.updated_at >= since)
        members = q.all()
        if not members:
            return

        loan_eids = {str(m.loan_id) for m in members}
        user_eids = {str(m.user_id) for m in members if m.user_id}
        rp_eids = {str(m.referral_partner_id) for m in members if m.referral_partner_id}

        node_cache: dict[tuple[str, str], KnowledgeGraphNode] = {}
        for ntype, eids in [("loan", loan_eids), ("user", user_eids), ("referral_partner", rp_eids)]:
            if not eids:
                continue
            for n in (
                self.db.query(KnowledgeGraphNode)
                .filter(
                    KnowledgeGraphNode.organization_id == self.organization_id,
                    KnowledgeGraphNode.node_type == ntype,
                    KnowledgeGraphNode.entity_id.in_(eids),
                )
                .all()
            ):
                node_cache[(n.node_type, n.entity_id)] = n

        for m in members:
            loan_node = node_cache.get(("loan", str(m.loan_id)))
            if not loan_node:
                continue

            if m.user_id:
                user_node = node_cache.get(("user", str(m.user_id)))
                if user_node:
                    self.graph.upsert_edge(
                        user_node.id, loan_node.id, "team_member_on",
                        properties={"role": m.role},
                    )
                    self._stats["edges_upserted"] += 1
            elif m.referral_partner_id:
                rp_node = node_cache.get(("referral_partner", str(m.referral_partner_id)))
                if rp_node:
                    self.graph.upsert_edge(
                        rp_node.id, loan_node.id, "team_member_on",
                        properties={"role": m.role},
                    )
                    self._stats["edges_upserted"] += 1
            else:
                contact_label = m.name or "Unknown"
                contact_node = self.graph.upsert_node(
                    "contact", f"ltm_{m.id}", contact_label,
                    _clean({"email": m.email, "phone": m.phone, "company": m.company, "role": m.role}),
                )
                self.graph.upsert_edge(contact_node.id, loan_node.id, "team_member_on", properties={"role": m.role})
                self._stats["nodes_upserted"] += 1
                self._stats["edges_upserted"] += 1

    def _sync_mum_clients(self, since: datetime | None = None) -> None:
        from database.models.referral import MUMClient

        q = self.db.query(MUMClient).filter(
            MUMClient.organization_id == self.organization_id,
        )
        if since and hasattr(MUMClient, "updated_at"):
            q = q.filter(MUMClient.updated_at >= since)
        elif since:
            q = q.filter(MUMClient.created_at >= since)

        for mc in q.all():
            label = mc.client_name or f"MUM #{mc.id}"
            props = {
                "loan_number": mc.loan_number,
                "status": mc.status,
                "original_rate": str(mc.original_rate) if mc.original_rate else None,
                "current_rate": str(mc.current_rate) if mc.current_rate else None,
                "refinance_opportunity": mc.refinance_opportunity,
                "engagement_score": mc.engagement_score,
            }
            node = self.graph.upsert_node("mum_client", str(mc.id), label, _clean(props))
            self._stats["nodes_upserted"] += 1

            if mc.user_id:
                user_node = self.graph.get_node("user", str(mc.user_id))
                if user_node:
                    self.graph.upsert_edge(user_node.id, node.id, "manages_mum")
                    self._stats["edges_upserted"] += 1

    # =====================================================================
    # Single-entity sync (for real-time updates on write)
    # =====================================================================

    def sync_lead(self, lead_id: int) -> None:
        from database.models.lead_loan import Lead

        lead = self.db.query(Lead).filter(Lead.id == lead_id, Lead.organization_id == self.organization_id).first()
        if not lead or lead.deleted_at:
            self.graph.delete_node("lead", str(lead_id))
            return

        label = lead.name or f"Lead #{lead.id}"
        props = {
            "email": lead.email, "phone": lead.phone, "stage": lead.stage,
            "source": lead.source, "ai_score": lead.ai_score,
            "loan_type": lead.loan_type, "loan_number": lead.loan_number,
        }
        node = self.graph.upsert_node("lead", str(lead.id), label, _clean(props))

        self.graph.delete_edges_for_target(node.id, ["owns_lead", "referred"])
        self.graph.delete_edges_for_source(node.id, ["co_applicant"])

        if lead.owner_id:
            owner_node = self.graph.get_node("user", str(lead.owner_id))
            if owner_node:
                self.graph.upsert_edge(owner_node.id, node.id, "owns_lead")
        if lead.referral_partner_id:
            rp_node = self.graph.get_node("referral_partner", str(lead.referral_partner_id))
            if rp_node:
                self.graph.upsert_edge(rp_node.id, node.id, "referred")
        if lead.co_applicant_email:
            co_label = lead.co_applicant_name or "Co-Applicant"
            co_node = self.graph.upsert_node(
                "contact", f"co_{lead.id}", co_label,
                _clean({"email": lead.co_applicant_email, "role": "co_applicant"}),
            )
            self.graph.upsert_edge(node.id, co_node.id, "co_applicant")

    def sync_loan(self, loan_id: int) -> None:
        from database.models.lead_loan import Lead, Loan

        loan = self.db.query(Loan).filter(Loan.id == loan_id, Loan.organization_id == self.organization_id).first()
        if not loan or loan.deleted_at:
            self.graph.delete_node("loan", str(loan_id))
            return

        label = _loan_label(loan)
        props = {
            "loan_number": loan.loan_number, "stage": loan.stage,
            "amount": str(loan.amount) if loan.amount else None,
            "loan_type": loan.loan_type,
            "rate": str(loan.rate) if loan.rate else None,
            "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
            "funded_date": loan.funded_date.isoformat() if loan.funded_date else None,
        }
        node = self.graph.upsert_node("loan", str(loan.id), label, _clean(props))

        self.graph.delete_edges_for_target(node.id, ["officers_loan", "has_loan"])

        if loan.loan_officer_id:
            lo_node = self.graph.get_node("user", str(loan.loan_officer_id))
            if lo_node:
                self.graph.upsert_edge(lo_node.id, node.id, "officers_loan")
        if loan.loan_number:
            lead = (
                self.db.query(Lead)
                .filter(Lead.organization_id == self.organization_id, Lead.loan_number == loan.loan_number, Lead.deleted_at == None)
                .first()
            )
            if lead:
                lead_node = self.graph.get_node("lead", str(lead.id))
                if lead_node:
                    self.graph.upsert_edge(lead_node.id, node.id, "has_loan")

    # =====================================================================
    # Helpers
    # =====================================================================

    def _cleanup_stale_edges(self) -> None:
        """Remove edges whose backing FK relationships no longer hold.

        Batch-loads all edges and nodes into dicts, then validates against
        backing tables in bulk — avoids N+1 queries.
        """
        from database.models.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode
        from database.models.lead_loan import Lead, Loan
        from database.models.core import User
        from database.models.referral import MUMClient, ReferralPartner

        org = self.organization_id
        stale_count = 0

        revalidate_types = [
            "owns_lead", "officers_loan", "referred", "works_with", "manages",
            "in_branch", "manages_mum",
        ]

        edges = (
            self.db.query(KnowledgeGraphEdge)
            .filter(
                KnowledgeGraphEdge.organization_id == org,
                KnowledgeGraphEdge.relationship_type.in_(revalidate_types),
            )
            .all()
        )
        if not edges:
            self._stats["edges_removed"] = 0
            return

        node_ids = set()
        for e in edges:
            node_ids.add(e.source_node_id)
            node_ids.add(e.target_node_id)

        nodes = (
            self.db.query(KnowledgeGraphNode)
            .filter(KnowledgeGraphNode.id.in_(node_ids))
            .all()
        )
        node_map = {n.id: n for n in nodes}

        lead_ids = _safe_int_set(n.entity_id for n in nodes if n.node_type == "lead")
        loan_ids = _safe_int_set(n.entity_id for n in nodes if n.node_type == "loan")
        user_ids = _safe_int_set(n.entity_id for n in nodes if n.node_type == "user")
        rp_ids = _safe_int_set(n.entity_id for n in nodes if n.node_type == "referral_partner")

        lead_fks = {}
        if lead_ids:
            for l in self.db.query(Lead.id, Lead.owner_id, Lead.referral_partner_id).filter(Lead.id.in_(lead_ids), Lead.deleted_at == None).all():
                lead_fks[l.id] = (str(l.owner_id) if l.owner_id else None, str(l.referral_partner_id) if l.referral_partner_id else None)

        loan_fks = {}
        if loan_ids:
            for l in self.db.query(Loan.id, Loan.loan_officer_id).filter(Loan.id.in_(loan_ids), Loan.deleted_at == None).all():
                loan_fks[l.id] = str(l.loan_officer_id) if l.loan_officer_id else None

        user_fks = {}
        if user_ids:
            for u in self.db.query(User.id, User.manager_id, User.branch_id).filter(User.id.in_(user_ids), User.is_active == True).all():
                user_fks[u.id] = (
                    str(u.manager_id) if u.manager_id else None,
                    str(u.branch_id) if u.branch_id else None,
                )

        rp_fks = {}
        if rp_ids:
            for r in self.db.query(ReferralPartner.id, ReferralPartner.owner_id).filter(ReferralPartner.id.in_(rp_ids)).all():
                rp_fks[r.id] = str(r.owner_id) if r.owner_id else None

        mum_ids = _safe_int_set(n.entity_id for n in nodes if n.node_type == "mum_client")
        mum_fks = {}
        if mum_ids:
            for m in self.db.query(MUMClient.id, MUMClient.user_id).filter(MUMClient.id.in_(mum_ids)).all():
                mum_fks[m.id] = str(m.user_id) if m.user_id else None

        for edge in edges:
            src = node_map.get(edge.source_node_id)
            tgt = node_map.get(edge.target_node_id)
            if not src or not tgt:
                self.db.delete(edge)
                stale_count += 1
                continue

            try:
                tgt_eid = int(tgt.entity_id)
            except (ValueError, TypeError):
                continue

            valid = True
            rt = edge.relationship_type

            if rt == "owns_lead":
                fk = lead_fks.get(tgt_eid)
                valid = fk is not None and fk[0] == src.entity_id
            elif rt == "officers_loan":
                fk = loan_fks.get(tgt_eid)
                valid = fk is not None and fk == src.entity_id
            elif rt == "referred":
                fk = lead_fks.get(tgt_eid)
                valid = fk is not None and fk[1] == src.entity_id
            elif rt == "manages":
                fk = user_fks.get(tgt_eid)
                valid = fk is not None and fk[0] == src.entity_id
            elif rt == "works_with":
                fk = rp_fks.get(tgt_eid)
                valid = fk is not None and fk == src.entity_id
            elif rt == "in_branch":
                try:
                    src_eid = int(src.entity_id)
                except (ValueError, TypeError):
                    continue
                fk = user_fks.get(src_eid)
                valid = fk is not None and fk[1] == tgt.entity_id
            elif rt == "manages_mum":
                fk = mum_fks.get(tgt_eid)
                valid = fk is not None and fk == src.entity_id

            if not valid:
                self.db.delete(edge)
                stale_count += 1

        if stale_count:
            self.db.flush()
            logger.info(f"Cleaned up {stale_count} stale edges for org {org}")
        self._stats["edges_removed"] = stale_count

    def _cleanup_deleted_nodes(self) -> None:
        """Remove graph nodes for deleted leads/loans and orphaned contacts."""
        from database.models.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode
        from database.models.lead_loan import Lead, Loan
        from sqlalchemy import or_

        org = self.organization_id
        deleted_count = 0

        for node_type, Model in [("lead", Lead), ("loan", Loan)]:
            graph_nodes = (
                self.db.query(KnowledgeGraphNode.id, KnowledgeGraphNode.entity_id)
                .filter(
                    KnowledgeGraphNode.organization_id == org,
                    KnowledgeGraphNode.node_type == node_type,
                )
                .all()
            )
            if not graph_nodes:
                continue

            entity_id_map: dict[int, int] = {}
            for node_id, eid in graph_nodes:
                try:
                    entity_id_map[int(eid)] = node_id
                except (ValueError, TypeError):
                    pass

            if not entity_id_map:
                continue

            live_ids = set(
                r[0] for r in self.db.query(Model.id)
                .filter(Model.id.in_(entity_id_map.keys()), Model.deleted_at == None)
                .all()
            )

            orphan_node_ids = [nid for eid, nid in entity_id_map.items() if eid not in live_ids]
            if orphan_node_ids:
                self.db.query(KnowledgeGraphNode).filter(
                    KnowledgeGraphNode.id.in_(orphan_node_ids),
                ).delete(synchronize_session="fetch")
                deleted_count += len(orphan_node_ids)

        if deleted_count:
            self.db.flush()

        edge_exists = (
            self.db.query(KnowledgeGraphEdge.id)
            .filter(
                or_(
                    KnowledgeGraphEdge.source_node_id == KnowledgeGraphNode.id,
                    KnowledgeGraphEdge.target_node_id == KnowledgeGraphNode.id,
                )
            )
            .correlate(KnowledgeGraphNode)
            .exists()
        )
        orphan_contact_ids = [
            nid for (nid,) in self.db.query(KnowledgeGraphNode.id)
            .filter(
                KnowledgeGraphNode.organization_id == org,
                KnowledgeGraphNode.node_type == "contact",
                ~edge_exists,
            )
            .all()
        ]
        if orphan_contact_ids:
            self.db.query(KnowledgeGraphNode).filter(
                KnowledgeGraphNode.id.in_(orphan_contact_ids),
            ).delete(synchronize_session="fetch")
            deleted_count += len(orphan_contact_ids)

        if deleted_count:
            self.db.flush()
            logger.info(f"Cleaned up {deleted_count} orphan nodes for org {org}")
        self._stats["nodes_removed"] = deleted_count

    def _ensure_branch_node(self, branch_id: int) -> Any:
        existing = self.graph.get_node("branch", str(branch_id))
        if existing:
            return existing
        from database.models.core import Branch

        branch = self.db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == self.organization_id).first()
        if not branch:
            return None
        node = self.graph.upsert_node(
            "branch", str(branch.id), branch.name,
            _clean({"company": branch.company, "nmls_id": branch.nmls_id}),
        )
        self._stats["nodes_upserted"] += 1
        return node


# ---- module helpers ---------------------------------------------------------

def _safe_int_set(values) -> set[int]:
    result = set()
    for v in values:
        try:
            result.add(int(v))
        except (ValueError, TypeError):
            pass
    return result


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _user_label(user: Any) -> str:
    parts = []
    if getattr(user, "first_name", None):
        parts.append(user.first_name)
    if getattr(user, "last_name", None):
        parts.append(user.last_name)
    return " ".join(parts) if parts else user.email


def _loan_label(loan: Any) -> str:
    name = loan.borrower_name or "Unknown Borrower"
    number = loan.loan_number or f"Loan #{loan.id}"
    return f"{name} — {number}"


def _rp_weight(rp: Any) -> float:
    """Heavier weight for more productive referral relationships."""
    closed = rp.closed_loans or 0
    if closed >= 10:
        return 3.0
    if closed >= 5:
        return 2.0
    if closed >= 1:
        return 1.5
    return 1.0
