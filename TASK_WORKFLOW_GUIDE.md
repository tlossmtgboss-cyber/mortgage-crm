# Task & Workflow Management Guide

## Overview

The Task & Workflow Management system allows administrators to efficiently onboard new employees by uploading tasks in bulk, assigning pre-configured workflows, and creating individual tasks.

**Location:** Settings → Task & Workflow Management

---

## Features

### 1. 📤 Bulk Task Upload

Upload multiple tasks at once using a CSV file. Perfect for importing task lists or setting up multiple tasks for a new employee.

#### CSV Format

Your CSV file should have the following columns:

```
title,description,priority,due_date,category,status
```

**Column Definitions:**
- **title** (required): Task title/name
- **description** (optional): Detailed description of the task
- **priority**: low | medium | high | urgent (default: medium)
- **due_date**: Date in YYYY-MM-DD format (e.g., 2025-12-01)
- **category**: general | onboarding | training | setup | meeting | review
- **status**: pending | in_progress | completed (default: pending)

#### Example CSV File

```csv
title,description,priority,due_date,category,status
Complete onboarding checklist,Review all onboarding materials,high,2025-12-01,onboarding,pending
Set up email signature,Configure professional email signature,medium,2025-11-25,setup,pending
Schedule 1-on-1 with manager,Initial check-in meeting,high,2025-11-22,meeting,pending
Review company handbook,Read and acknowledge policies,high,2025-11-23,onboarding,pending
Complete compliance training,Finish regulatory training modules,high,2025-12-05,training,pending
```

#### How to Use

1. Click on **"Bulk Upload"** tab
2. Select the user you want to assign tasks to
3. Upload your CSV file
4. Preview the first 5 rows to verify format
5. Click **"Upload Tasks"**

---

### 2. 🔄 Assign Workflow

Assign pre-configured workflow templates that automatically create multiple related tasks. Great for standardized onboarding processes.

#### Available Workflows

1. **New Employee Onboarding** (8 tasks)
   - Complete employee information form
   - Review company handbook
   - Set up workstation and accounts
   - Complete compliance training
   - Schedule 1-on-1 with manager
   - Meet the team
   - Review systems and tools
   - 30-day check-in

2. **Loan Officer Setup** (5 tasks)
   - Complete NMLS registration
   - Learn CRM lead management
   - Review loan products and guidelines
   - Shadow experienced LO
   - Set up email signature and marketing materials

3. **Processor Training** (4 tasks)
   - Learn loan processing workflow
   - Master document collection
   - Practice with test files
   - Learn underwriting guidelines

4. **Underwriter Onboarding** (4 tasks)
   - Review underwriting authority and guidelines
   - Complete underwriting certification
   - Shadow senior underwriter
   - Review sample underwriting scenarios

#### How to Use

1. Click on **"Assign Workflow"** tab
2. Select the user
3. Choose a workflow from the dropdown
4. Preview the tasks that will be created
5. Click **"Assign Workflow"**

**Note:** Due dates are automatically calculated based on each task's timeframe (e.g., 1 day, 3 days, 7 days, etc.)

---

### 3. ➕ Create Single Task

Create a single task quickly without uploading a CSV or using a workflow.

#### How to Use

1. Click on **"Create Single Task"** tab
2. Select the user to assign to
3. Fill in task details:
   - **Title** (required)
   - **Description** (optional)
   - **Priority**: Low, Medium, High, or Urgent
   - **Category**: General, Onboarding, Training, Setup, Meeting, or Review
   - **Due Date** (optional)
4. Click **"Create Task"**

---

## Use Cases

### Onboarding a New Employee

**Recommended Approach:**
1. Use **Assign Workflow** to apply the "New Employee Onboarding" workflow
2. Add role-specific workflow (Loan Officer Setup, Processor Training, etc.)
3. Use **Create Single Task** to add any custom, organization-specific tasks

### Importing Existing Task List

**Recommended Approach:**
1. Create a CSV file with all tasks
2. Use **Bulk Upload** to import all tasks at once

### Quick Ad-hoc Tasks

**Recommended Approach:**
1. Use **Create Single Task** for one-off assignments

---

## Best Practices

### For Administrators

1. **Standardize Workflows**: Use consistent workflows for the same roles
2. **Update Regularly**: Keep workflow templates current with process changes
3. **Set Clear Due Dates**: Help employees prioritize tasks
4. **Use Categories**: Makes task filtering and reporting easier
5. **Assign Appropriate Priorities**: Reserve "urgent" for truly time-sensitive tasks

### For CSV Files

1. **Test First**: Upload a small test file before bulk importing
2. **Validate Dates**: Ensure dates are in YYYY-MM-DD format
3. **Check Spelling**: Task titles and descriptions should be professional
4. **Save Template**: Keep a template CSV file for future use
5. **Remove Headers**: If re-uploading, ensure only one header row exists

### For Workflows

1. **Review Before Assigning**: Check the task preview before assigning
2. **Customize After Assignment**: Edit tasks after creation if needed
3. **Document Changes**: If modifying workflows, document for consistency

---

## Sample CSV Template

Download and customize this template:

**File: task_upload_template.csv**

```csv
title,description,priority,due_date,category,status
Complete employee information form,Fill out all required personal and tax information,high,2025-11-22,onboarding,pending
Review company handbook,Read and acknowledge company policies and procedures,high,2025-11-24,onboarding,pending
Set up workstation and accounts,Configure email computer and necessary software accounts,high,2025-11-22,setup,pending
Complete compliance training,Finish all required regulatory and compliance training modules,high,2025-11-28,training,pending
Schedule 1-on-1 with manager,Initial check-in meeting to discuss role and expectations,high,2025-11-23,meeting,pending
Meet the team,Introduction meetings with key team members and stakeholders,medium,2025-11-26,meeting,pending
Review systems and tools,Training on CRM communication tools and other systems,high,2025-11-28,training,pending
30-day check-in,Review progress and address any questions or concerns,medium,2025-12-21,review,pending
```

---

## Troubleshooting

### Upload Failed

**Problem**: CSV upload returns an error

**Solutions:**
1. Check CSV format matches exactly (comma-separated, correct column names)
2. Ensure file is saved as CSV, not Excel (.xlsx)
3. Verify dates are in YYYY-MM-DD format
4. Check for special characters that might break CSV format
5. Ensure at least the "title" column has values

### Tasks Not Appearing

**Problem**: Tasks were created but don't show in user's task list

**Solutions:**
1. Verify the correct user was selected
2. Check user has proper permissions to view tasks
3. Refresh the Tasks page
4. Check task filters (status, category, etc.)

### Workflow Assignment Failed

**Problem**: Workflow assignment returns an error

**Solutions:**
1. Ensure user is selected
2. Verify user is active in the system
3. Check backend logs for specific error
4. Try assigning again

### Wrong User Assigned

**Problem**: Tasks were assigned to the wrong user

**Solutions:**
1. Navigate to Tasks page
2. Bulk select the tasks
3. Use "Reassign" feature to move to correct user
4. Or delete and recreate with correct user

---

## API Reference

For developers integrating with the task management system:

### Bulk Upload
```
POST /api/v1/tasks/bulk-upload
Content-Type: multipart/form-data

Body:
- file: CSV file
- assigned_to: User ID (integer)
```

### Get Workflows
```
GET /api/v1/workflows?category=onboarding
```

### Get Workflow Details
```
GET /api/v1/workflows/{workflow_id}
```

### Assign Workflow
```
POST /api/v1/workflows/{workflow_id}/assign
Content-Type: application/json

Body:
{
  "user_id": 123
}
```

### Create Single Task
```
POST /api/v1/tasks
Content-Type: application/json

Body:
{
  "title": "Task title",
  "description": "Task description",
  "priority": "high",
  "due_date": "2025-12-01",
  "category": "onboarding",
  "assigned_to": 123
}
```

---

## Future Enhancements

Planned features for future releases:

- [ ] Custom workflow builder
- [ ] Task templates library
- [ ] Bulk task editing
- [ ] Task dependencies
- [ ] Automated reminders
- [ ] Progress tracking dashboards
- [ ] Task completion analytics
- [ ] Excel file support (.xlsx)
- [ ] Task duplication/cloning
- [ ] Workflow versioning

---

## Support

Need help?

1. Check this guide first
2. Review the sample CSV template
3. Test with a small file before bulk import
4. Contact your CRM administrator
5. Create a support ticket if issues persist

---

**Last Updated**: November 18, 2025
**Version**: 1.0.0
**Status**: ✅ Production Ready
