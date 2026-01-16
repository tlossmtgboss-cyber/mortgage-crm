# Dynamic Documents Needed Feature - Integration Guide

## Overview

This document explains how to integrate the new **Dynamic Documents Needed** feature into the mortgage application. This feature automatically tracks and displays required documents as borrowers complete their application, then pushes these requirements to the client portal upon submission.

## Feature Components

### 1. Frontend Component

**Location:** `frontend/src/pages/applications/components/DocumentsNeeded.js`

The `DocumentsNeeded` component:
- Dynamically evaluates application answers to determine required documents
- Groups documents by category (income, assets, property, etc.)
- Displays required vs optional documents with badges
- Syncs with backend API to create lead_conditions records
- Updates in real-time as the user answers questions

### 2. Styling

**Location:** `frontend/src/pages/applications/components/DocumentsNeeded.css`

Professional styling with:
- Responsive design for mobile/desktop
- Category-based color coding
- Smooth hover effects
- Custom scrollbar styling
- Sticky positioning for sidebar display

### 3. Backend Integration

**Database Table:** `lead_conditions` (already exists)

Schema:
```sql
- id: Primary key
- lead_id: Links to leads table
- name: Document name
- description: What's needed
- category: Document category
- priority: 'required' or 'optional'
- status: 'pending', 'received', etc.
- due_date: Optional deadline
- created_at, updated_at: Timestamps
```

## Integration Steps

### Step 1: Add to Application Shell

Edit `frontend/src/pages/applications/components/ApplicationShell.js`:

```javascript
import DocumentsNeeded from './DocumentsNeeded';

// In your ApplicationShell component:
<div className="application-container">
  <div className="application-main">
    {/* Existing stage/question rendering */}
  </div>
  
  <div className="application-sidebar">
    <DocumentsNeeded 
      applicationData={formData}
      workspaceId={workspaceId}
    />
  </div>
</div>
```

### Step 2: Update ApplicationShell.css

Add sidebar layout styles to `ApplicationShell.css`:

```css
.application-container {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.application-main {
  min-width: 0; /* Prevent grid overflow */
}

.application-sidebar {
  position: relative;
}

@media (max-width: 1024px) {
  .application-container {
    grid-template-columns: 1fr;
  }
}
```

### Step 3: Pass Application Data

Ensure the ApplicationShell passes the current form data to DocumentsNeeded:

```javascript
const [formData, setFormData] = useState({});

// When answers are updated:
const handleAnswerChange = (questionId, value) => {
  setFormData(prev => ({
    ...prev,
    [questionId]: value
  }));
};
```

### Step 4: Create Backend API Endpoint

Create `backend/routes/documents_routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import LeadCondition, PURLWorkspace

router = APIRouter()

@router.post("/api/workspaces/{workspace_id}/documents")
async def sync_documents(
    workspace_id: int,
    documents: List[dict],
    db: Session = Depends(get_db)
):
    """
    Sync required documents for a workspace/lead.
    Creates or updates lead_conditions records.
    """
    # Get workspace and linked lead_id
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id
    ).first()
    
    if not workspace or not workspace.lead_id:
        raise HTTPException(status_code=404, detail="Workspace or lead not found")
    
    # Clear existing pending documents for this lead
    db.query(LeadCondition).filter(
        LeadCondition.lead_id == workspace.lead_id,
        LeadCondition.status == 'pending'
    ).delete()
    
    # Create new document requirements
    for doc in documents:
        lead_condition = LeadCondition(
            lead_id=workspace.lead_id,
            name=doc['name'],
            description=doc['description'],
            category=doc['category'],
            priority=doc['priority'],
            status='pending',
            is_new=True
        )
        db.add(lead_condition)
    
    db.commit()
    
    return {"success": True, "count": len(documents)}
```

### Step 5: Register the Route

In `backend/main.py`:

```python
from routes import documents_routes

app.include_router(documents_routes.router, tags=["documents"])
```

### Step 6: Update Application Submission

In your application submission handler, ensure documents are pushed to client portal:

```javascript
const handleSubmitApplication = async () => {
  try {
    // Submit application
    await submitApplication(formData);
    
    // Documents are already synced via DocumentsNeeded component
    // They will automatically appear in the client portal
    
    // Redirect to success page
    navigate('/application/submitted');
  } catch (error) {
    console.error('Submission error:', error);
  }
};
```

## Document Evaluation Rules

The component evaluates these conditions to determine required documents:

### Employment Documents
- **W-2 Employee:** Pay stubs (30 days) + W-2 forms (2 years)
- **Self-Employed:** Tax returns (2 years) + P&L + Bank statements (2 months)

### Asset Documents
- **Savings:** Bank statements (2 months)
- **Gift:** Gift letter + Donor proof of funds
- **Retirement:** 401k/IRA statements (optional)

### Property Documents
- **Purchase Contract:** Fully executed agreement
- **Condo:** HOA documents required

### Additional Income
- **Rental/Alimony:** Income documentation
- **Rental Property:** Lease agreements

### Credit/Debt
- **Student Loans:** Current statement
- **Bankruptcy/Foreclosure:** Discharge papers

### Identity (Always Required)
- Government-issued ID (Driver's license or passport)

## Customizing Document Rules

To add custom document rules, edit the `evaluateDocumentRequirements` function in `DocumentsNeeded.js`:

```javascript
// Add custom rule
if (data.customCondition === 'value') {
  requiredDocs.push({
    name: 'Custom Document',
    description: 'Description of what's needed',
    category: 'custom_category',
    priority: 'required'
  });
}
```

## Client Portal Integration

Documents pushed to `lead_conditions` table automatically appear in the client portal's "Documents Needed" section. The portal should:

1. Query `lead_conditions` where `lead_id` matches the client's lead
2. Display documents grouped by category
3. Allow document upload for each requirement
4. Update status to 'received' upon upload
5. Set `is_new` to false after first viewing

## Testing

### Frontend Testing
1. Start application flow
2. Answer questions that trigger document requirements
3. Verify documents appear in sidebar in real-time
4. Check categorization and badges
5. Verify responsive design on mobile

### Backend Testing
```bash
# Test document sync endpoint
curl -X POST http://localhost:8000/api/workspaces/123/documents \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "name": "Pay Stubs",
        "description": "Last 30 days",
        "category": "income",
        "priority": "required"
      }
    ]
  }'
```

### Database Verification
```sql
-- Check created documents
SELECT * FROM lead_conditions 
WHERE lead_id = YOUR_LEAD_ID 
ORDER BY created_at DESC;
```

## Deployment Checklist

- [ ] Commit DocumentsNeeded.js and .css files
- [ ] Create backend API endpoint
- [ ] Update ApplicationShell to include component
- [ ] Test document evaluation rules
- [ ] Verify backend sync works
- [ ] Test client portal display
- [ ] Update environment variables if needed
- [ ] Deploy frontend and backend changes
- [ ] Test on staging environment
- [ ] Deploy to production

## Environment Variables

Add to `.env` if needed:

```
REACT_APP_API_URL=http://localhost:8000
```

## Troubleshooting

### Documents not appearing
- Check console for API errors
- Verify workspaceId is passed correctly
- Ensure application data structure matches expected field names

### Backend sync failing
- Verify workspace has linked lead_id
- Check database permissions
- Review FastAPI logs for errors

### Styling issues
- Clear browser cache
- Check CSS import in component
- Verify no conflicting styles

## Future Enhancements

Potential improvements:
- Document upload directly from application
- Progress indicators (3/10 documents provided)
- Email notifications when documents are needed
- Document templates/examples
- AI-powered document suggestions based on loan type
- Integration with document OCR/parsing
- Automatic document request emails

## Support

For questions or issues with this feature, contact the development team or file an issue in the repository.
