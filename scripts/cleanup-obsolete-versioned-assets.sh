#!/usr/bin/env bash
set -euo pipefail

# Execute na raiz do projeto VemDeDelivery.
# Remove somente assets antigos já substituídos pelos nomes estáveis.
rm -f \
  static/js/admin/payment-account-v4.js \
  static/js/admin/payment-account-v5.js \
  static/js/admin/payment-account-v6.js \
  static/js/admin/payment-account-v7.js \
  static/js/admin/payment-account-v8.js \
  static/js/admin/payment-account-v9.js \
  static/css/admin/payment-account-v7.css \
  static/css/admin/payment-account-v8.css \
  static/css/admin/payment-account-v9.css \
  static/css/admin-v2.css \
  static/css/customer-brand-v4.css

# Remove metadados de download do Windows que eventualmente vieram no ZIP.
find . -type f -name '*:Zone.Identifier' -delete

echo '✅ Assets antigos e Zone.Identifier removidos.'
