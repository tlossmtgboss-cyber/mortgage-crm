# Data Upload & Import Guide

## 🎯 Overview

The Data Management feature allows you to import data from Excel (.xlsx, .xls) or CSV files into your CRM. AI analyzes your file, asks clarifying questions, and helps map columns to the correct fields.

---

## 📍 How to Access

1. Login to your CRM
2. Click **Settings** (⚙️)
3. Select **Data Management** tab
4. Or navigate directly to: `/settings` → Data Management

---

## 📤 Supported File Formats

- ✅ **CSV** (.csv)
- ✅ **Excel** (.xlsx, .xls)
- ✅ **Maximum file size**: No limit (practical limit ~10MB recommended)
- ✅ **Maximum rows**: No limit (tested with 10,000+ rows)

---

## 🚀 Upload Process

### Step 1: Select File

**Options:**
- **Drag & drop** your file into the upload area
- **Click "Choose File"** to browse and select

**File validation:**
- Checks file type
- Verifies it's CSV or Excel
- Shows file name and size

### Step 2: AI Analysis

AI automatically:
- Reads your file structure
- Identifies column headers
- Analyzes sample data
- Generates clarifying questions
- Suggests column mappings

**What you'll see:**
- Data preview (first 5 rows)
- Total row count
- AI-generated questions
- Suggested mappings

### Step 3: Answer Questions

AI asks questions to understand your data:

**Primary Question:**
```
"Where should this data be imported?"
```

**Options:**
1. **👤 Leads**
   - Prospect contacts who haven't started an application yet
   - Use for: Cold leads, referrals, website inquiries

2. **📄 Active Clients (Loans)**
   - Active loan applications in process
   - Use for: Applications, pre-approvals, loans in pipeline

3. **💼 Portfolio (MUM Clients)**
   - Existing clients with closed loans (Client for Life Engine)
   - Use for: Past clients, servicing portfolio, retention database

### Step 4: Map Columns

Review AI's suggested column mappings and adjust as needed.

**Your File Column** → **CRM Field**

Example:
```
First Name → first_name
Last Name → last_name
Email → email
Phone → phone
Loan Amount → loan_amount
```

**Options for each column:**
- **Map to a field**: Select from dropdown
- **Skip this column**: Leave as "Skip this column"

### Step 5: Import Data

Click **"Import Data →"**

AI will:
- Validate each row
- Transform data as needed
- Create records in your CRM
- Report results

### Step 6: View Results

**Success summary shows:**
- Total records processed
- Successfully imported
- Failed imports (with error details)
- Destination (where data was imported)

---

## 📊 Field Mappings

### Leads Fields

| CRM Field | Description | Type |
|-----------|-------------|------|
| `first_name` | First Name | Text |
| `last_name` | Last Name | Text |
| `email` | Email Address | Email |
| `phone` | Phone Number | Text |
| `address` | Street Address | Text |
| `city` | City | Text |
| `state` | State (2-letter code) | Text |
| `zip_code` | ZIP Code | Text |
| `property_value` | Property Value | Number |
| `loan_amount` | Desired Loan Amount | Number |
| `down_payment` | Down Payment Amount | Number |
| `employment_status` | Employment Status | Text |
| `annual_income` | Annual Income | Number |
| `credit_score` | Credit Score | Number |
| `notes` | Additional Notes | Text |

### Active Loans Fields

| CRM Field | Description | Type |
|-----------|-------------|------|
| `loan_number` | Loan Number (auto-generated if missing) | Text |
| `borrower_name` | Borrower Full Name | Text |
| `co_borrower_name` | Co-Borrower Name | Text |
| `property_address` | Property Address | Text |
| `loan_amount` / `amount` | Loan Amount | Number |
| `interest_rate` / `rate` | Interest Rate | Number |
| `loan_term` / `term` | Term in months | Number |
| `loan_type` | Loan Type (FHA, VA, Conv) | Text |
| `loan_purpose` | Purchase/Refi/Cash-out | Text |
| `closing_date` | Closing Date | Date |
| `lender` | Lender Name | Text |
| `processor` | Processor Name | Text |
| `underwriter` | Underwriter Name | Text |

### Portfolio (MUM) Fields

| CRM Field | Description | Type |
|-----------|-------------|------|
| `loan_number` | Loan Number (auto-generated if missing) | Text |
| `borrower_name` | Client Name | Text |
| `property_address` | Property Address | Text |
| `original_loan_amount` | Original Loan Amount | Number |
| `current_balance` | Current Balance | Number |
| `interest_rate` / `current_rate` | Interest Rate | Number |
| `monthly_payment` | Monthly Payment | Number |
| `origination_date` | Origination Date | Date |
| `maturity_date` | Maturity Date | Date |
| `last_payment_date` | Last Payment Date | Date |
| `payment_status` | Payment Status | Text |

---

## 🤖 AI Features

### Automatic Field Detection

AI automatically detects and maps:
- ✅ Name fields (First, Last, Full Name)
- ✅ Contact info (Email, Phone)
- ✅ Address fields (City, State, ZIP)
- ✅ Financial fields (Loan Amount, Income, Credit Score)
- ✅ Common variations (eg. "Loan Amt" → `loan_amount`)

### Automatic Data Transformation

AI automatically:
- ✅ Combines first + last name if needed
- ✅ Generates loan numbers if missing
- ✅ Maps field variations (loan_amount ↔ amount)
- ✅ Skips empty/null values
- ✅ Converts data types (text → number for amounts)

### Smart Validation

AI validates:
- Required fields (name, loan_number, etc.)
- Data types (numbers, emails, dates)
- Field constraints
- Unique values (loan numbers)

---

## ✅ Best Practices

### File Preparation

1. **Use clear column headers**
   - ✅ "First Name" instead of "FN"
   - ✅ "Email" instead of "E-mail Address"
   - ✅ "Loan Amount" instead of "Amt"

2. **Keep data clean**
   - Remove empty rows
   - Remove duplicate headers
   - Use consistent formatting

3. **Format numbers correctly**
   - Remove currency symbols ($)
   - Remove commas (350,000 → 350000)
   - Or keep them - AI will clean them

4. **Date format**
   - Use: YYYY-MM-DD, MM/DD/YYYY, or MM-DD-YYYY
   - AI will parse most common formats

### Column Naming Tips

**Good column names:**
- First Name, Last Name
- Email Address, Email
- Phone Number, Phone, Mobile
- Loan Amount, Amount
- Annual Income, Yearly Income
- Credit Score, FICO Score

**AI will recognize these variations:**
- "Loan Amt" → loan_amount
- "Property Val" → property_value
- "Down Pmt" → down_payment

---

## ⚠️ Common Issues & Solutions

### Issue: "Failed to analyze file"

**Solutions:**
- Ensure file is .csv, .xlsx, or .xls
- Check file isn't corrupted
- Verify file isn't empty
- Try re-saving file

### Issue: "Import failed" for some rows

**Common causes:**
1. **Missing required field**: Add required data
2. **Invalid data type**: Check numbers are numbers
3. **Duplicate values**: Loan numbers must be unique

**Check error details:**
- View error list on completion screen
- Shows which row failed and why

### Issue: Wrong destination selected

**Solution:**
- Click "Cancel" or "← Back"
- Start over with correct destination

### Issue: Columns not mapping correctly

**Solution:**
- Manually adjust mappings in Step 3
- Use dropdown to select correct CRM field
- Or select "Skip this column"

---

## 📝 Example Files

### Example 1: Lead Import

**CSV/Excel structure:**
```
First Name | Last Name | Email              | Phone        | Loan Amount | Credit Score
John       | Doe       | john@example.com   | 555-123-4567 | 450000      | 720
Jane       | Smith     | jane@example.com   | 555-234-5678 | 380000      | 695
```

**Import to:** Leads
**Result:** 2 new leads created

### Example 2: Loan Import

**CSV/Excel structure:**
```
Loan Number | Borrower Name | Loan Amount | Rate | Term | Closing Date
LOAN-001    | John Doe      | 450000      | 6.5  | 360  | 2024-12-15
LOAN-002    | Jane Smith    | 380000      | 6.75 | 360  | 2024-12-20
```

**Import to:** Active Clients (Loans)
**Result:** 2 active loans created

### Example 3: Portfolio Import

**CSV/Excel structure:**
```
Loan Number | Borrower     | Original Amount | Current Balance | Rate | Monthly Payment
MUM-001     | Bob Johnson  | 350000          | 325000          | 4.5  | 1773
MUM-002     | Mary Williams| 425000          | 400000          | 5.0  | 2282
```

**Import to:** Portfolio (MUM Clients)
**Result:** 2 MUM clients created

---

## 🎯 Testing Your Import

### Test with Sample Data

1. Create small test file (3-5 rows)
2. Import to appropriate destination
3. Verify data appears correctly
4. Check all fields mapped correctly
5. Then import full dataset

### Verify After Import

1. Navigate to appropriate section:
   - Leads: Go to Leads page
   - Loans: Go to Active Loans page
   - Portfolio: Go to Portfolio page

2. Look for your imported data
3. Click on a record to view details
4. Confirm all fields populated correctly

---

## 🔒 Security & Privacy

- ✅ **Encrypted uploads**: All file uploads use HTTPS
- ✅ **User authentication**: Must be logged in to upload
- ✅ **Data ownership**: Imports tied to your user account
- ✅ **No data retention**: Files not stored after processing
- ✅ **Secure processing**: Processed in memory only

---

## 💡 Pro Tips

1. **Start small**: Test with 5-10 rows first
2. **Use templates**: Save your mapping preferences
3. **Clean data first**: Remove junk rows before import
4. **Check duplicates**: Avoid importing same data twice
5. **Backup first**: Export existing data before large imports
6. **Use loan numbers**: Makes tracking easier
7. **Review mappings**: Don't trust AI blindly - verify mappings

---

## 📞 Need Help?

If you encounter issues:

1. Check error messages carefully
2. Review this guide
3. Try with smaller file
4. Check file format and data quality
5. Contact support with:
   - Error message
   - Sample of your file (anonymized)
   - What you're trying to import

---

**🎯 The data upload feature is now live and ready to use!**

**Access it at:** Settings → Data Management
