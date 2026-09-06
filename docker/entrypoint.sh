#!/bin/sh
set -e

echo "Ожидание PostgreSQL по адресу ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
until nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
  sleep 0.5
done
echo "PostgreSQL доступен."

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

# Наполнение пустой базы демо-данными (idempotent): врачи, админ, пациенты,
# слоты. Иначе после чистого `docker compose up` сценарии врача/админа
# невозможно потрогать. Отключается переменной SEED_DEMO_DATA=false.
if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  python manage.py seed_demo_data || echo "seed_demo_data пропущен (не критично)."
fi

exec "$@"
