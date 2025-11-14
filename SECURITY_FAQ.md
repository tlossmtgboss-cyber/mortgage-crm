# Security FAQ - Quick Reference Guide

## For Sales Calls & Customer Questions

---

### **Q1: "Is my client data secure?"**

**Answer:**
*"Yes, absolutely. We use bank-level AES-128 encryption for all sensitive borrower data like credit scores, income, and loan amounts. This means your client information is encrypted before it's stored and can't be read even if someone accessed the database. We also use HTTPS encryption for all data transmission, just like online banking."*

**Key Points:**
- Bank-level encryption (AES-128)
- Data encrypted at rest and in transit
- Same security as online banking

---

### **Q2: "Are you GLBA compliant?"**

**Answer:**
*"Yes, we are fully GLBA compliant. The Gramm-Leach-Bliley Act requires financial institutions to protect customer information, and we meet all requirements including administrative, technical, and physical safeguards. We encrypt sensitive financial data, maintain access controls, and follow all GLBA privacy rules."*

**Key Points:**
- ✅ Fully GLBA compliant
- Meets federal requirements for financial data
- Regular compliance audits

---

### **Q3: "What if there's a data breach?"**

**Answer:**
*"While we have robust security measures in place including 24/7 monitoring and threat detection, if a breach occurred we would: (1) immediately investigate and contain it, (2) notify all affected customers within 72 hours, (3) provide full transparency about what happened, and (4) implement remediation measures. However, because all sensitive data is encrypted, even a database breach would not expose readable client information."*

**Key Points:**
- 72-hour notification
- Data is encrypted (not readable)
- Incident response protocols in place

---

### **Q4: "Can your employees see my client data?"**

**Answer:**
*"Only authorized personnel with a legitimate business need can access customer data, and all access is logged and monitored. We use role-based access controls, meaning employees can only see what they need to do their job. Additionally, sensitive financial information is encrypted, so even authorized users see protected data."*

**Key Points:**
- Role-based access control
- All access is logged
- Sensitive data encrypted

---

### **Q5: "Do you sell our data to third parties?"**

**Answer:**
*"No, never. We don't sell, share, or use your data for any purpose other than providing you with CRM service. Your data is yours. We only share data with third-party services that you explicitly authorize (like Microsoft 365 or Twilio), and those integrations use secure OAuth connections with minimum permissions."*

**Key Points:**
- We NEVER sell data
- No third-party sharing without permission
- You own your data

---

### **Q6: "What certifications do you have?"**

**Answer:**
*"We are GLBA and GDPR compliant, and we're currently pursuing SOC 2 Type II certification, which is the gold standard for SaaS security audits. We also follow security best practices from NIST, OWASP, and other industry standards."*

**Key Points:**
- ✅ GLBA Compliant
- ✅ GDPR Compliant
- 🔄 SOC 2 Type II (in progress)

---

### **Q7: "How is data backed up?"**

**Answer:**
*"We perform automated daily backups with encrypted storage. Backups are retained for disaster recovery purposes and are secured with the same encryption standards as your live data. You can also export your data at any time."*

**Key Points:**
- Automated daily backups
- Encrypted backup storage
- Export data anytime

---

### **Q8: "What about integrations with Microsoft/Twilio/etc?"**

**Answer:**
*"All third-party integrations use OAuth 2.0, which is the industry-standard secure authorization protocol. We only request the minimum permissions needed, and we store all integration tokens encrypted. You can revoke access at any time. We never share your CRM data with these services without your explicit authorization."*

**Key Points:**
- OAuth 2.0 (industry standard)
- Minimum permissions only
- You control access

---

### **Q9: "Is this secure enough for our compliance officer?"**

**Answer:**
*"Yes. We meet the same compliance standards required of financial institutions. We can provide detailed security documentation, answer technical security questionnaires, and connect your compliance officer with our security team for any specific requirements. Many regulated mortgage companies already use our platform."*

**Key Points:**
- Financial-grade compliance
- Detailed documentation available
- Security team available for questions

---

### **Q10: "What happens if I want to delete my data?"**

**Answer:**
*"You have complete control. You can export all your data at any time, and if you close your account, we permanently delete your data from our systems within 30 days. This is part of our GDPR compliance—you have the right to data portability and the right to erasure."*

**Key Points:**
- Export data anytime
- Permanent deletion within 30 days
- GDPR "right to erasure"

---

## 🎯 **The 30-Second Pitch**

*"Our CRM uses the same security standards as online banking—bank-level encryption, GLBA compliance, and enterprise infrastructure. Your client data is encrypted before storage, protected in transit with HTTPS, and we never share or sell your information. We're built specifically for mortgage professionals who need to meet compliance requirements."*

---

## 📧 **For Written Follow-ups**

**Email Template:**

> Hi [Name],
>
> Great question about security. Here's a quick overview:
>
> **Encryption:** We use AES-128 encryption (bank-level) for all sensitive data
> **Compliance:** Fully GLBA and GDPR compliant
> **Infrastructure:** Enterprise cloud hosting with 99.9% uptime
> **Privacy:** We never sell or share your data
> **Monitoring:** 24/7 security monitoring and threat detection
>
> We can provide detailed security documentation, and our security team is available to answer any technical questions from your compliance officer.
>
> Security overview: [Link to SECURITY_ONE_PAGER.md]
>
> Let me know if you'd like to schedule a call with our security team.
>
> Best,
> [Your Name]

---

## 🚨 **Red Flags to Avoid**

**DON'T SAY:**
- ❌ "We've never been hacked" (you can't guarantee this)
- ❌ "We're 100% secure" (nothing is 100% secure)
- ❌ "We don't need compliance because..." (always meet compliance)
- ❌ "Your data is on our servers" (say "encrypted cloud infrastructure")

**DO SAY:**
- ✅ "We use bank-level encryption"
- ✅ "We're GLBA compliant"
- ✅ "We follow industry best practices"
- ✅ "Your data is encrypted at rest and in transit"

---

## 📞 **When to Escalate**

Forward to security team (security@mortgagecrm.com) if customer asks:
- Detailed penetration test results
- SOC 2 report (when available)
- Specific technical implementation details
- Custom security requirements for enterprise
- BAA (Business Associate Agreement) for HIPAA

---

**Last Updated:** November 2024

*Keep this document handy for sales calls and customer conversations.*
