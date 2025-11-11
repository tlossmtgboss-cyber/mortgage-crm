# Buyer Intake Application

## Overview
The Buyer Intake Application is a public, shareable form that interested homebuyers can complete. When submitted, all fields automatically populate a lead profile in your CRM with complete data.

## Shareable URL
```
https://mortgage-crm-nine.vercel.app/apply
```

**This URL requires NO authentication** - anyone can access and submit the form.

## Form Sections

### 1. Contact Information
- First Name, Last Name
- Email, Phone
- Preferred Contact Method (Text/Email/Phone)

### 2. Scenario
- Occupancy (Primary Residence, Second Home, Investment)
- Timeline (0-30 days, 31-60 days, 61-90 days, 90+ days, Just researching)
- Target Area (City or ZIP)

### 3. Budget
- Price Target
- Down Payment (% or $)
- Comfortable Monthly Payment (PITI)

### 4. Profile
- Estimated Credit Range (760+, 740-759, 700-739, etc.)
- First-time Buyer (Yes/No)
- VA Eligible (Yes/No)
- Employment Type (W2, Self-Employed, 1099, Retired)
- Annual Household Income
- Liquid Assets for Closing
- Self-Employed (Yes/No)

### 5. Co-Borrower (Optional)
- Add Co-Borrower option
- First Name, Last Name
- Annual Income

### 6. Partners & Preferences
- Working with Realtor (Yes/No)
- Agent Name, Agent Email
- Letter Type (Full Pre-Approval, Pre-Qualification)
- Communication Preferences (Text, Email, Phone)

### 7. Consents & Notes
- Soft Credit Pull Authorization
- Contact Consent (Required)
- Additional Notes

## How Data Maps to Lead Profile

### Direct Field Mapping:
| Form Field | Lead Field | Description |
|-----------|------------|-------------|
| First Name + Last Name | `name` | Full borrower name |
| Email | `email` | Contact email |
| Phone | `phone` | Contact phone |
| Co-Borrower Name | `co_applicant_name` | Co-borrower full name |
| Price Target | `loan_amount`, `preapproval_amount`, `property_value` | Desired property price |
| Down Payment | `down_payment` | Calculated down payment amount |
| Household Income | `annual_income` | Annual pre-tax income |
| Employment Type | `employment_status` | Employment classification |
| First-time Buyer | `first_time_buyer` | Boolean flag |
| Occupancy | `property_type` | Primary, Second Home, or Investment |

### Intelligent Lead Classification:
- **Loan Type**: Automatically determined
  - VA eligible → "VA"
  - First-time buyer + price < $500k → "FHA"
  - Otherwise → "Conventional"

- **Lead Stage**: Set to "NEW"
- **Source**: "Buyer Intake Form"
- **AI Score**: Calculated automatically based on profile
- **Next Action**: Generated from timeline and occupancy
  - Example: "Contact within 0-30 days - Buyer interested in Primary Residence"

### Complete Data Storage:
ALL form data is preserved in the lead's `user_metadata` JSON field under `buyer_intake`:
- Contact details
- Scenario (timeline, location)
- Budget (monthly comfort, down payment type)
- Profile (credit range, VA status, self-employed, liquid assets)
- Co-borrower info
- Agent/Realtor info
- Communication preferences
- Consents (soft credit pull, contact consent)
- Submission timestamp

## How to Share

### Method 1: Direct Link
Share this URL directly via:
- Email
- Text message
- Website
- Social media
- Print materials

### Method 2: QR Code
Generate a QR code pointing to:
```
https://mortgage-crm-nine.vercel.app/apply
```

### Method 3: Embed on Website
```html
<iframe src="https://mortgage-crm-nine.vercel.app/apply"
        width="100%"
        height="800px"
        frameborder="0">
</iframe>
```

## Viewing Submitted Leads

1. Log into your CRM
2. Navigate to **Leads** page
3. Look for leads with:
   - **Source**: "Buyer Intake Form"
   - **Stage**: "NEW"
4. Click on any lead to see full details
5. All buyer intake data is preserved in the lead profile

## Features

### User Experience:
- ✅ Clean, modern design with gradient header
- ✅ Mobile-responsive (works on all devices)
- ✅ Takes ~2 minutes to complete
- ✅ Real-time validation
- ✅ Success confirmation message

### Data Security:
- ✅ Secure HTTPS connection
- ✅ Input validation
- ✅ No authentication required (public form)
- ✅ Consent checkboxes for credit pull and contact

### CRM Integration:
- ✅ Automatic lead creation
- ✅ AI scoring
- ✅ Intelligent loan type detection
- ✅ Complete data preservation
- ✅ Assigned to primary user automatically

## Example Use Cases

1. **Agent Referrals**: Share link with real estate agents to pre-qualify their buyers
2. **Website Integration**: Embed on your mortgage company website
3. **Social Media**: Post link in Facebook groups, Instagram bio
4. **Email Campaigns**: Include in email signatures and newsletters
5. **Print Marketing**: Add QR code to business cards, flyers, yard signs
6. **Open Houses**: Share link with attendees for quick pre-qualification

## Customization

The form can be customized by modifying:
- **Frontend**: `/frontend/src/pages/BuyerIntake.js`
- **Styling**: `/frontend/src/pages/BuyerIntake.css`
- **Backend Logic**: `/backend/main.py` (search for `buyer-intake`)

## Support

If a buyer has issues submitting the form, they will see an error message. Contact your CRM administrator for support.

---

**URL to Share**: https://mortgage-crm-nine.vercel.app/apply
