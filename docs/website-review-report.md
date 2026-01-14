# Website Review Report

## Scope
- Focused on identifying likely unfinished work (TODOs, placeholders, and hard-coded defaults) in frontend and backend.
- Commands run:
  - `rg -n "TODO|FIXME|XXX|HACK|TBD|unfinished" /workspace/mortgage-crm/frontend /workspace/mortgage-crm/backend`
  - `sed -n '250,320p' /workspace/mortgage-crm/frontend/src/pages/portal/ActiveLoanPortal.jsx`
  - `sed -n '520,620p' /workspace/mortgage-crm/backend/routes/accounting/ap_routes.py`
  - `sed -n '450,520p' /workspace/mortgage-crm/backend/routes/accounting/ar_routes.py`
  - `sed -n '60,120p' /workspace/mortgage-crm/backend/routes/accounting/chart_of_accounts_routes.py`
  - `sed -n '320,380p' /workspace/mortgage-crm/backend/routes/accounting/chart_of_accounts_routes.py`
  - `sed -n '960,1025p' /workspace/mortgage-crm/backend/routes/call_transfer_routes.py`
  - `sed -n '1000,1040p' /workspace/mortgage-crm/backend/services/calendar_sync_service.py`
