-- Fix voicemail_drops table to add missing columns

-- Add campaign_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'campaign_id') THEN
        ALTER TABLE voicemail_drops ADD COLUMN campaign_id INTEGER REFERENCES voicemail_campaigns(id) ON DELETE SET NULL;
        CREATE INDEX idx_voicemail_drops_campaign ON voicemail_drops(campaign_id);
    END IF;
END $$;

-- Add template_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'template_id') THEN
        ALTER TABLE voicemail_drops ADD COLUMN template_id INTEGER REFERENCES voicemail_templates(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add contact_name column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'contact_name') THEN
        ALTER TABLE voicemail_drops ADD COLUMN contact_name VARCHAR(255);
    END IF;
END $$;

-- Add contact_email column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'contact_email') THEN
        ALTER TABLE voicemail_drops ADD COLUMN contact_email VARCHAR(255);
    END IF;
END $$;

-- Rename columns if they have old names
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'voicemail_drops' AND column_name = 'recipient_name') THEN
        ALTER TABLE voicemail_drops RENAME COLUMN recipient_name TO contact_name_old;
    END IF;
END $$;

-- Add message_variables column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'message_variables') THEN
        ALTER TABLE voicemail_drops ADD COLUMN message_variables JSONB;
    END IF;
END $$;

-- Add audio_url column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'audio_url') THEN
        ALTER TABLE voicemail_drops ADD COLUMN audio_url VARCHAR(500);
    END IF;
END $$;

-- Add vapi_assistant_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'vapi_assistant_id') THEN
        ALTER TABLE voicemail_drops ADD COLUMN vapi_assistant_id VARCHAR(255);
    END IF;
END $$;

-- Rename status column if it has old name
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'voicemail_drops' AND column_name = 'delivery_status') THEN
        ALTER TABLE voicemail_drops RENAME COLUMN delivery_status TO status;
    END IF;
END $$;

-- Add delivery_attempts column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'delivery_attempts') THEN
        ALTER TABLE voicemail_drops ADD COLUMN delivery_attempts INTEGER DEFAULT 0;
    END IF;
END $$;

-- Add last_attempt_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'last_attempt_at') THEN
        ALTER TABLE voicemail_drops ADD COLUMN last_attempt_at TIMESTAMP;
    END IF;
END $$;

-- Add delivered_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'delivered_at') THEN
        ALTER TABLE voicemail_drops ADD COLUMN delivered_at TIMESTAMP;
    END IF;
END $$;

-- Add call_duration column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'call_duration') THEN
        ALTER TABLE voicemail_drops ADD COLUMN call_duration INTEGER;
    END IF;
END $$;

-- Add call_cost column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'call_cost') THEN
        ALTER TABLE voicemail_drops ADD COLUMN call_cost DECIMAL(10, 4);
    END IF;
END $$;

-- Add carrier column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'carrier') THEN
        ALTER TABLE voicemail_drops ADD COLUMN carrier VARCHAR(50);
    END IF;
END $$;

-- Add voicemail_listened column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'voicemail_listened') THEN
        ALTER TABLE voicemail_drops ADD COLUMN voicemail_listened BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Add listened_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'listened_at') THEN
        ALTER TABLE voicemail_drops ADD COLUMN listened_at TIMESTAMP;
    END IF;
END $$;

-- Add callback_received column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'callback_received') THEN
        ALTER TABLE voicemail_drops ADD COLUMN callback_received BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Add callback_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'callback_at') THEN
        ALTER TABLE voicemail_drops ADD COLUMN callback_at TIMESTAMP;
    END IF;
END $$;

-- Add callback_notes column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'callback_notes') THEN
        ALTER TABLE voicemail_drops ADD COLUMN callback_notes TEXT;
    END IF;
END $$;

-- Add error_code column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'error_code') THEN
        ALTER TABLE voicemail_drops ADD COLUMN error_code VARCHAR(50);
    END IF;
END $$;

-- Add retry_scheduled_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'retry_scheduled_at') THEN
        ALTER TABLE voicemail_drops ADD COLUMN retry_scheduled_at TIMESTAMP;
    END IF;
END $$;

-- Add updated_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'voicemail_drops' AND column_name = 'updated_at') THEN
        ALTER TABLE voicemail_drops ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
    END IF;
END $$;
