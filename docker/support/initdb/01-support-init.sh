#!/bin/bash
# Runs once on first Postgres boot (docker-entrypoint-initdb.d).
# Creates the RLS-enforced app role; the schema itself (tables + policies)
# is applied idempotently by the service on startup via the owner DSN.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	DO \$\$
	BEGIN
	  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'support_api_app') THEN
	    CREATE ROLE support_api_app LOGIN;
	  END IF;
	END \$\$;
	ALTER ROLE support_api_app WITH LOGIN PASSWORD '${SUPPORT_APP_DB_PASSWORD}';
SQL
