-- HirePath: database schema
-- Run ONCE as the database owner (Supabase SQL editor, or psql as postgres).
-- Safe to re-run: every statement is idempotent.
--
-- After running this file, give the app role a password in a SEPARATE query
-- that you do not save or commit:
--   ALTER ROLE jobtracker_app WITH PASSWORD '<a long random password>';

BEGIN;

-- ---------------------------------------------------------------------------
-- Tables (prefixed with jobtracker_ because the Supabase project is shared)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS jobtracker_users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The backend lowercases emails; the CHECK makes the database enforce it too,
    -- so "Amina@x.com" and "amina@x.com" can never be two accounts.
    email         text NOT NULL UNIQUE
                  CHECK (email = lower(email) AND char_length(email) BETWEEN 3 AND 254),
    password_hash text NOT NULL CHECK (char_length(password_hash) > 0),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobtracker_applications (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        bigint NOT NULL REFERENCES jobtracker_users (id) ON DELETE CASCADE,
    company        text NOT NULL CHECK (char_length(btrim(company)) BETWEEN 1 AND 120),
    role           text NOT NULL CHECK (char_length(btrim(role)) BETWEEN 1 AND 120),
    url            text CHECK (url IS NULL OR (char_length(url) <= 2048 AND url ~* '^https?://')),
    status         text NOT NULL DEFAULT 'Applied'
                   CHECK (status IN ('Applied', 'Interview', 'Offer', 'Rejected')),
    follow_up_date date,
    -- When you applied. Defaults to today; imports can set it to an earlier date.
    -- Used for the "applications per week" chart.
    applied_on     date NOT NULL DEFAULT CURRENT_DATE,
    notes          text CHECK (notes IS NULL OR char_length(notes) <= 2000),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- jobtracker_users.email: no extra index needed. The UNIQUE constraint already
-- creates one, and it serves the login lookup (WHERE email = $1).

-- Every application query filters by user_id (ownership), and the board can
-- filter by status too. This composite index covers both "WHERE user_id = $1"
-- and "WHERE user_id = $1 AND status = $2", and it also serves as the index on
-- the foreign key, so ON DELETE CASCADE from users does not scan the table.
CREATE INDEX IF NOT EXISTS jobtracker_applications_user_status_idx
    ON jobtracker_applications (user_id, status);

-- Every status an application has been in, oldest first. The board only shows
-- the current status; this history is what lets the stats page say "reached an
-- interview" even after an application was later rejected.
CREATE TABLE IF NOT EXISTS jobtracker_status_events (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id bigint NOT NULL REFERENCES jobtracker_applications (id) ON DELETE CASCADE,
    status         text NOT NULL CHECK (status IN ('Applied', 'Interview', 'Offer', 'Rejected')),
    changed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobtracker_status_events_application_idx
    ON jobtracker_status_events (application_id, status);

-- ---------------------------------------------------------------------------
-- Restricted app role (least privilege)
-- ---------------------------------------------------------------------------

-- Created WITHOUT a password, so it cannot log in until the owner sets one.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jobtracker_app') THEN
        CREATE ROLE jobtracker_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO jobtracker_app;

-- Users: the app only registers and looks up users. No UPDATE or DELETE.
GRANT SELECT, INSERT ON jobtracker_users TO jobtracker_app;

-- Applications: full CRUD on rows, but no ALTER, DROP or TRUNCATE.
GRANT SELECT, INSERT, UPDATE, DELETE ON jobtracker_applications TO jobtracker_app;

-- History is append-only for the app: no UPDATE or DELETE (rows go away only
-- through ON DELETE CASCADE when the application itself is deleted).
GRANT SELECT, INSERT ON jobtracker_status_events TO jobtracker_app;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
-- RLS is on, so any role WITHOUT a policy (e.g. Supabase's anon and
-- authenticated roles used by the Data API) sees zero rows.
-- The app role gets a policy; per-user ownership is enforced by the backend
-- in every query (WHERE user_id = <id from the JWT>).

ALTER TABLE jobtracker_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobtracker_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobtracker_status_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS jobtracker_app_users ON jobtracker_users;
CREATE POLICY jobtracker_app_users ON jobtracker_users
    FOR ALL TO jobtracker_app USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS jobtracker_app_applications ON jobtracker_applications;
CREATE POLICY jobtracker_app_applications ON jobtracker_applications
    FOR ALL TO jobtracker_app USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS jobtracker_app_status_events ON jobtracker_status_events;
CREATE POLICY jobtracker_app_status_events ON jobtracker_status_events
    FOR ALL TO jobtracker_app USING (true) WITH CHECK (true);

-- Supabase grants table access to anon/authenticated by default. Remove it
-- (only if those roles exist, so this file also runs on plain Postgres).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON jobtracker_users, jobtracker_applications, jobtracker_status_events FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON jobtracker_users, jobtracker_applications, jobtracker_status_events FROM authenticated;
    END IF;
END
$$;

COMMIT;
