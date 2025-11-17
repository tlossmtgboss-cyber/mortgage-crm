# Onboarding Wizard Redesign Plan

## Overview
Complete restructure of the onboarding wizard from 9 steps to 10 steps with full-page layout.

## Current State (9 Steps)
1. Process Upload
2. Role Review
3. Task Review
4. Team & Roles
5. Process Tree
6. Integrations
7. Compliance
8. AI Agent
9. Test & Go-Live

## New Requirements (10 Steps + Overview)

### Step 0: Overview Page
- Shows all 10 steps with time estimates
- Budget planning information
- Start button to begin onboarding

### Step 1: User Registration
- Name
- Email
- Phone
- Business address
- Current role
- Business hours

### Step 2: Team Members Setup
- Name and email for each team member
- Permission assignment
- CSV/XLS upload template option for mass onboarding

### Step 3: Upload Process Documents
- Upload roles and responsibilities documents
- AI Smart Assistant reviews and extracts:
  - Process roles
  - Responsibilities
  - Creates tasks for review

### Step 4: Assign Users to Roles
- Assign team members to roles/responsibilities
- Modify roles and responsibilities
- Add additional tasks

### Step 5: Review Individual Team Members
- Review each team member's tasks
- Add missing tasks
- Approve assignments

### Step 6: Data Parsing Demo
- Upload 3 sample emails
- AI parses and shows reconciliation preview
- Preview matches actual reconciliation page layout

### Step 7: Data Upload Templates
- Provide templates for 3 uploads:
  1. Leads
  2. Active Loans
  3. Closed Clients (MUM)
- Instructions for each template

### Step 8: Review Data to Import
- Review all data to be added
- Approve import

### Step 9: Connect Integrations
- Connect third-party services
- Calendar, Email, etc.

### Step 10: Software Functions Setup
- Phone number configuration
- Choose Smart AI Receptionist voice
- Call routing rules:
  - Leads → Production Partner
  - Active Loans → Processing Assistant
  - MUM Clients → Schedule on LO calendar

## Technical Changes Required

### Layout
- [ ] Change from box layout to full-page layout
- [ ] Update CSS for full-page experience
- [ ] Add proper header/footer

### State Management
- [ ] Add Step 0 state
- [ ] Update totalSteps from 9 to 10
- [ ] Add new formData fields for all steps
- [ ] Implement save/resume functionality

### Step Indicators
- [ ] Update step labels to match new flow
- [ ] Add time estimates to each step
- [ ] Show current progress

### Rendering
- [ ] Create renderOverview() for Step 0
- [ ] Update all step rendering functions
- [ ] Add CSV/XLS upload components
- [ ] Add email parsing preview
- [ ] Add data upload templates

### API Integration
- [ ] Auto-save progress
- [ ] Resume from saved state
- [ ] Send team member invitation emails

## Priority Order
1. Update totalSteps and structure
2. Create overview page (Step 0)
3. Update step 1-2 (basic registration + team)
4. Update steps 3-5 (process & task assignment)
5. Create steps 6-8 (data upload & review)
6. Update steps 9-10 (integrations & AI receptionist)
7. Change layout to full-page
8. Add save/resume functionality
