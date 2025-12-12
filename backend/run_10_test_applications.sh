#!/bin/bash

# Run 10 test mortgage applications
# Each will create a lead, generate documents, and send email to admin

BASE_URL="https://mortgage-crm-production-7a9a.up.railway.app"
ADMIN_LO_ID="57"

echo "============================================================"
echo "RUNNING 10 TEST MORTGAGE APPLICATIONS"
echo "============================================================"
echo "Target: $BASE_URL"
echo "Loan Officer ID: $ADMIN_LO_ID"
echo "============================================================"

SUCCESSFUL=0
FAILED=0

submit_application() {
    local TEST_NUM=$1
    local FIRST_NAME=$2
    local LAST_NAME=$3
    local CITY=$4
    local STATE=$5
    local PROPERTY_TYPE=$6
    local EMPLOYER=$7
    local JOB_TITLE=$8
    local LOAN_PROGRAM=$9
    local PRICE=${10}
    local DOWN=${11}
    local SALARY=${12}

    local EMAIL="test.$(echo $FIRST_NAME | tr '[:upper:]' '[:lower:]').$(echo $LAST_NAME | tr '[:upper:]' '[:lower:]')$RANDOM@testapplication.com"
    local PHONE="555-$((RANDOM % 900 + 100))-$((RANDOM % 9000 + 1000))"
    local CHECKING=$((RANDOM % 40000 + 10000))
    local SAVINGS=$((RANDOM % 80000 + 20000))
    local INVESTMENTS=$((RANDOM % 100000))

    echo ""
    echo "============================================================"
    echo "TEST $TEST_NUM/10: $FIRST_NAME $LAST_NAME"
    echo "============================================================"
    echo "  Property: \$$PRICE in $CITY, $STATE"
    echo "  Loan Type: $LOAN_PROGRAM"
    echo "  Down Payment: \$$DOWN"
    echo "  Annual Income: \$$SALARY"

    # Create JSON payload using heredoc
    local JSON_PAYLOAD
    read -r -d '' JSON_PAYLOAD << EOJSON
{
    "profileData": {
        "firstName": "$FIRST_NAME",
        "lastName": "$LAST_NAME",
        "email": "$EMAIL",
        "phone": "$PHONE",
        "address": "$((RANDOM % 9000 + 100)) Main Street",
        "city": "$CITY",
        "state": "$STATE",
        "zip": "$((RANDOM % 90000 + 10000))"
    },
    "incomeData": {
        "employerName": "$EMPLOYER",
        "jobTitle": "$JOB_TITLE",
        "startDate": "2020-01-15",
        "annualSalary": $SALARY
    },
    "assetData": {
        "checking": $CHECKING,
        "savings": $SAVINGS,
        "investments": $INVESTMENTS,
        "giftAmount": 0
    },
    "propertyData": {
        "address": "$((RANDOM % 9000 + 100)) Oak Avenue",
        "city": "$CITY",
        "state": "$STATE",
        "zip": "$((RANDOM % 90000 + 10000))",
        "county": "$CITY County",
        "propertyType": "$PROPERTY_TYPE",
        "occupancy": "primary",
        "purchasePrice": $PRICE,
        "downPayment": $DOWN,
        "loanProgram": "$LOAN_PROGRAM"
    },
    "declarations": {
        "citizenship": "us_citizen",
        "first_time_buyer": "yes"
    },
    "paymentEstimate": {
        "monthlyPayment": $((($PRICE - $DOWN) * 6 / 1000)),
        "rate": 6.875
    },
    "eConsentAgreed": true,
    "creditAuthAgreed": true,
    "loId": "$ADMIN_LO_ID"
}
EOJSON

    # Submit application
    local RESPONSE
    RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/borrower-auth/submit-application" \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD" \
        --max-time 60 2>&1)

    # Check result
    if echo "$RESPONSE" | grep -q '"success"'; then
        local LEAD_ID
        LEAD_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('lead_id','N/A'))" 2>/dev/null || echo "N/A")
        local PDFS
        PDFS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('pdfs_generated',False))" 2>/dev/null || echo "N/A")
        local FANNIE
        FANNIE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('fannie_mae_generated',False))" 2>/dev/null || echo "N/A")
        local EMAIL_SENT
        EMAIL_SENT=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('email_sent_to_lo',False))" 2>/dev/null || echo "N/A")
        local DOCS_STORED
        DOCS_STORED=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('documents_stored',[]))" 2>/dev/null || echo "[]")

        echo ""
        echo "  SUCCESS!"
        echo "  Lead ID: $LEAD_ID"
        echo "  PDFs Generated: $PDFS"
        echo "  Fannie Mae Generated: $FANNIE"
        echo "  Email Sent: $EMAIL_SENT"
        echo "  Documents Stored: $DOCS_STORED"

        SUCCESSFUL=$((SUCCESSFUL + 1))
        echo "OK|$TEST_NUM|$FIRST_NAME $LAST_NAME|$LEAD_ID" >> /tmp/test_results.txt
    else
        echo ""
        echo "  FAILED!"
        echo "  Response: ${RESPONSE:0:300}"

        FAILED=$((FAILED + 1))
        echo "FAIL|$TEST_NUM|$FIRST_NAME $LAST_NAME|" >> /tmp/test_results.txt
    fi
}

# Clear previous results
rm -f /tmp/test_results.txt
touch /tmp/test_results.txt

# Run 10 tests
submit_application 1 "Michael" "Anderson" "Los Angeles" "CA" "Single Family" "Tech Corp Inc" "Software Engineer" "Conventional" 450000 90000 125000
sleep 3
submit_application 2 "Jennifer" "Thompson" "San Diego" "CA" "Condo" "Healthcare Solutions LLC" "Nurse Manager" "FHA" 380000 19000 95000
sleep 3
submit_application 3 "David" "Martinez" "San Francisco" "CA" "Townhouse" "Finance Partners" "Financial Analyst" "VA" 650000 130000 175000
sleep 3
submit_application 4 "Sarah" "Johnson" "Sacramento" "CA" "Single Family" "Education First" "Teacher" "Conventional" 420000 84000 85000
sleep 3
submit_application 5 "Robert" "Williams" "Austin" "TX" "Single Family" "Manufacturing Co" "Production Manager" "Conventional" 550000 110000 110000
sleep 3
submit_application 6 "Emily" "Brown" "Denver" "CO" "Condo" "Retail Giants" "Store Manager" "FHA" 325000 16250 72000
sleep 3
submit_application 7 "William" "Davis" "Seattle" "WA" "Single Family" "Service Industries" "Consultant" "Conventional" 780000 156000 185000
sleep 3
submit_application 8 "Jessica" "Garcia" "Portland" "OR" "Townhouse" "Construction Pros" "Project Manager" "VA" 495000 24750 98000
sleep 3
submit_application 9 "James" "Miller" "Phoenix" "AZ" "Single Family" "Legal Associates" "Attorney" "Conventional" 620000 124000 165000
sleep 3
submit_application 10 "Ashley" "Wilson" "Miami" "FL" "Condo" "Media Group" "Marketing Director" "FHA" 510000 102000 115000

echo ""
echo "============================================================"
echo "TEST SUMMARY"
echo "============================================================"
echo "Successful: $SUCCESSFUL"
echo "Failed: $FAILED"
echo ""
echo "Results:"
while IFS='|' read -r status num name lead_id; do
    if [ "$status" = "OK" ]; then
        echo "  [OK] Test $num: $name (Lead ID: $lead_id)"
    else
        echo "  [X]  Test $num: $name - FAILED"
    fi
done < /tmp/test_results.txt

echo ""
echo "============================================================"
echo "TEST COMPLETE"
echo "============================================================"
