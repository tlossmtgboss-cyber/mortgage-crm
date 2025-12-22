-- Migration: Link Steve Latterson's lead to Timothy Loss (referral partner ID 22)
-- This fixes the case where an application was submitted before the referral partner linking fix was deployed

-- Update any leads with name containing "Steve Latterson" or "Latterson" to link to Timothy Loss
UPDATE leads
SET referral_partner_id = 22,
    updated_at = NOW()
WHERE (LOWER(name) LIKE '%latterson%' OR LOWER(name) LIKE '%steve latterson%')
  AND (referral_partner_id IS NULL OR referral_partner_id != 22);

-- Also check in loans table for any direct loan records
UPDATE loans
SET referral_partner_id = 22,
    updated_at = NOW()
WHERE (LOWER(borrower_name) LIKE '%latterson%' OR LOWER(borrower_name) LIKE '%steve latterson%')
  AND (referral_partner_id IS NULL OR referral_partner_id != 22);

-- Log the update for verification
SELECT 'Updated leads:' as action, id, name, referral_partner_id
FROM leads
WHERE LOWER(name) LIKE '%latterson%';

SELECT 'Updated loans:' as action, id, borrower_name, referral_partner_id
FROM loans
WHERE LOWER(borrower_name) LIKE '%latterson%';
