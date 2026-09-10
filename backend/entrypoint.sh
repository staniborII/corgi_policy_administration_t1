#!/bin/sh
set -e

echo "Starting Corgi backend..."

# Wait for database connectivity (RDS Proxy may take a moment on cold start)
echo "Waiting for database..."
python <<'PYEOF'
import os, sys, time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import connections
from django.db.utils import OperationalError

retries = 30
for i in range(retries):
    try:
        connections["default"].ensure_connection()
        print("Database is ready.")
        sys.exit(0)
    except OperationalError as e:
        print(f"Database not ready ({i + 1}/{retries}): {e}")
        time.sleep(2)

print("Database connection failed after maximum retries.")
sys.exit(1)
PYEOF

# Resolve FRONTEND_URL from SSM if not already set
if [ -z "$FRONTEND_URL" ] && [ -n "$FRONTEND_URL_SSM_PARAM" ]; then
    echo "Resolving frontend URL from SSM parameter: $FRONTEND_URL_SSM_PARAM"
    FRONTEND_URL=$(python <<'PYEOF' || true
import boto3, os, sys
try:
    client = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    resp = client.get_parameter(Name=os.environ["FRONTEND_URL_SSM_PARAM"])
    print(resp["Parameter"]["Value"], end="")
except Exception as e:
    print(f"WARNING: Could not read SSM parameter: {e}", file=sys.stderr)
PYEOF
    )
    if [ -n "$FRONTEND_URL" ]; then
        export FRONTEND_URL
        export CORS_ALLOWED_ORIGINS="$FRONTEND_URL"
        export CSRF_TRUSTED_ORIGINS="$FRONTEND_URL"
        CF_DOMAIN=$(echo "$FRONTEND_URL" | sed 's|https://||')
        export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS},${CF_DOMAIN}"
        echo "Resolved frontend URL: $FRONTEND_URL"
    else
        echo "WARNING: SSM parameter not available yet (first deploy?). CORS/CSRF will work after FrontendStack deploys and ECS restarts."
    fi
fi

# Run database migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files (Django admin CSS/JS)
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null

# Create superuser if credentials are provided and user doesn't exist
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Ensuring superuser exists..."
    python manage.py ensure_superuser
fi

echo "Starting application server..."
exec "$@"
