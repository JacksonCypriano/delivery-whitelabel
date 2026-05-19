#!/usr/bin/env bash
set -euo pipefail

echo "Running makemigrations..."
$DC exec web python manage.py makemigrations
echo "makemigrations finished."