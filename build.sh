#!/usr/bin/env bash
set -o errexit

python -m pip install --only-binary=pydantic-core -r requirements.txt

# ② インストールを確認
python -m pip show dj-database-url

python -c "import os; print('DATABASE_URL exists:', bool(os.getenv('DATABASE_URL')))"
python -c "import dj_database_url; print('Database ENGINE:', dj_database_url.config().get('ENGINE'))"

python - <<'PY'
import os
import django
import dj_database_url

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "myproject.settings"
)

django.setup()

from django.conf import settings

print("Settings module:", settings.SETTINGS_MODULE)

print(
    "DATABASE_URL exists:",
    bool(os.environ.get("DATABASE_URL"))
)

print(
    "Parsed ENGINE:",
    dj_database_url.config().get("ENGINE")
)

print(
    "Django ENGINE:",
    settings.DATABASES["default"].get("ENGINE")
)
PY
python manage.py migrate

# 初回の管理者ユーザー作成
if [ "$CREATE_SUPERUSER" = "true" ]; then
    python manage.py createsuperuser --noinput
fi