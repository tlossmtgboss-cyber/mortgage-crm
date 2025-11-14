-- Add external_message_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'incoming_data_events'
        AND column_name = 'external_message_id'
    ) THEN
        ALTER TABLE incoming_data_events
        ADD COLUMN external_message_id VARCHAR;

        CREATE INDEX idx_incoming_data_events_external_message_id
        ON incoming_data_events(external_message_id);

        RAISE NOTICE 'Successfully added external_message_id column with index';
    ELSE
        RAISE NOTICE 'Column external_message_id already exists';
    END IF;
END $$;
