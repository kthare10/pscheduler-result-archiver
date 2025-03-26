#!/bin/sh

# Wait for Redis to be ready
echo "Waiting for Redis..."
until nc -z redis 6379; do
  sleep 1
done

# Run migrations and start server
python manage.py migrate
exec "$@"
