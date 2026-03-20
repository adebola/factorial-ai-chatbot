ALTER TABLE tenant_settings
ADD COLUMN unknown_answer_behavior VARCHAR(20) DEFAULT 'decline' NOT NULL;
