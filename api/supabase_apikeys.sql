-- ==============================================================================
-- MetricSleuth Enterprise Step 4: API Keys for M2M Ingestion
-- ==============================================================================
-- Run these commands in the Supabase SQL Editor.
-- We only store the SHA-256 hash of the API key, never the plaintext key.

CREATE TABLE IF NOT EXISTS api_keys (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  key_prefix TEXT NOT NULL, -- The first 8 characters (e.g. sk_live_abc123) to show the user which key it is
  name TEXT NOT NULL,       -- e.g., "Airflow Prod Ingestion"
  last_used_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Policy 1: Users can read their own keys (prefix and name only)
CREATE POLICY "Users can view own API keys" 
ON api_keys FOR SELECT 
USING (auth.uid() = user_id);

-- Policy 2: Users can generate new keys
CREATE POLICY "Users can insert own API keys" 
ON api_keys FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- Policy 3: Users can revoke/delete their keys
CREATE POLICY "Users can delete own API keys" 
ON api_keys FOR DELETE 
USING (auth.uid() = user_id);

-- ==============================================================================
-- 🛑 Important Security Note:
-- The FastAPI backend uses the Supabase SERVICE_ROLE key to query this table 
-- by `key_hash` to authenticate incoming M2M requests, as the incoming request 
-- does not yet have a JWT `auth.uid()` identity established.
-- ==============================================================================
