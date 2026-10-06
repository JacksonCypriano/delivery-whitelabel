#!/usr/bin/env bash
set -euo pipefail

echo "Running makemigrations..."
$DC exec backend python manage.py makemigrations
echo "makemigrations finished."