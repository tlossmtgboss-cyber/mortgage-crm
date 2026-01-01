-- Seed Quiz Templates for Recruiting Assessment
-- Run this SQL directly on your PostgreSQL production database

-- First, ensure the table exists
CREATE TABLE IF NOT EXISTS recruit_quiz_templates (
    id SERIAL PRIMARY KEY,
    disposition VARCHAR(50) NOT NULL,
    question_text TEXT NOT NULL,
    question_type VARCHAR(20) DEFAULT 'likert',
    category VARCHAR(50) NOT NULL,
    weight DECIMAL(3,2) DEFAULT 1.0,
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_quiz_templates_disposition
    ON recruit_quiz_templates(disposition) WHERE is_active = true;

-- Screening stage questions
INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
SELECT * FROM (VALUES
    ('screening', 'How would you rate the candidate''s production volume based on their stated history?', 'likert', 'production', 1.0, 1),
    ('screening', 'Does the candidate have all required licenses and certifications?', 'yes_no', 'skills', 1.0, 2),
    ('screening', 'How consistent does their production history appear?', 'likert', 'production', 0.8, 3),
    ('screening', 'Rate the candidate''s initial enthusiasm about the opportunity', 'likert', 'culture_fit', 0.7, 4),
    ('screening', 'Does the candidate have experience with the loan types we focus on?', 'likert', 'skills', 0.9, 5)
) AS v(disposition, question_text, question_type, category, weight, display_order)
WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'screening');

-- Phone screen stage questions
INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
SELECT * FROM (VALUES
    ('phone_screen', 'How would you rate the candidate''s communication skills?', 'likert', 'skills', 1.0, 1),
    ('phone_screen', 'Rate the candidate''s level of enthusiasm during the call', 'likert', 'culture_fit', 0.9, 2),
    ('phone_screen', 'How coachable does the candidate appear to be?', 'likert', 'character', 1.0, 3),
    ('phone_screen', 'Rate the candidate''s professionalism', 'likert', 'character', 0.9, 4),
    ('phone_screen', 'How well did they articulate their production strategy?', 'likert', 'production', 0.8, 5),
    ('phone_screen', 'Does the candidate align with our company values?', 'likert', 'culture_fit', 1.0, 6)
) AS v(disposition, question_text, question_type, category, weight, display_order)
WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'phone_screen');

-- Interview stage questions
INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
SELECT * FROM (VALUES
    ('interview', 'Rate the candidate''s Dominance (D) personality trait', 'likert', 'disc', 1.0, 1),
    ('interview', 'Rate the candidate''s Influence (I) personality trait', 'likert', 'disc', 1.0, 2),
    ('interview', 'Rate the candidate''s Steadiness (S) personality trait', 'likert', 'disc', 1.0, 3),
    ('interview', 'Rate the candidate''s Conscientiousness (C) personality trait', 'likert', 'disc', 1.0, 4),
    ('interview', 'How would you rate the candidate''s integrity?', 'likert', 'character', 1.0, 5),
    ('interview', 'Rate the candidate''s resilience and ability to handle rejection', 'likert', 'character', 0.9, 6),
    ('interview', 'How strong is their work ethic?', 'likert', 'character', 1.0, 7),
    ('interview', 'Rate their technical knowledge of mortgage products', 'likert', 'skills', 1.0, 8),
    ('interview', 'How well do they understand the local market?', 'likert', 'skills', 0.8, 9),
    ('interview', 'Would they be a good cultural fit for the team?', 'likert', 'culture_fit', 1.0, 10)
) AS v(disposition, question_text, question_type, category, weight, display_order)
WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'interview');

-- Assessment stage questions
INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
SELECT * FROM (VALUES
    ('assessment', 'How did the candidate perform on the technical assessment?', 'likert', 'skills', 1.0, 1),
    ('assessment', 'Rate their product knowledge depth', 'likert', 'skills', 1.0, 2),
    ('assessment', 'How well did they handle scenario-based questions?', 'likert', 'skills', 0.9, 3),
    ('assessment', 'Rate their problem-solving abilities', 'likert', 'character', 0.9, 4),
    ('assessment', 'How realistic are their production projections?', 'likert', 'production', 1.0, 5)
) AS v(disposition, question_text, question_type, category, weight, display_order)
WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'assessment');

-- Offer stage questions
INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
SELECT * FROM (VALUES
    ('offer', 'Final assessment: Values alignment', 'likert', 'culture_fit', 1.0, 1),
    ('offer', 'Final assessment: Team compatibility', 'likert', 'culture_fit', 1.0, 2),
    ('offer', 'Final assessment: Growth potential', 'likert', 'production', 1.0, 3),
    ('offer', 'Final assessment: Leadership potential', 'likert', 'character', 0.8, 4),
    ('offer', 'Overall recommendation for hire', 'likert', 'culture_fit', 1.0, 5)
) AS v(disposition, question_text, question_type, category, weight, display_order)
WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'offer');

-- Verify the data was inserted
SELECT disposition, COUNT(*) as question_count
FROM recruit_quiz_templates
WHERE is_active = true
GROUP BY disposition
ORDER BY disposition;
