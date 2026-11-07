#!/usr/bin/env bash
set -o errexit

python -m pip install --only-binary=pydantic-core -r requirements.txt

# ② インストールを確認
python -m pip show dj-database-url

python -c "import os; print('DATABASE_URL exists:', bool(os.getenv('DATABASE_URL')))"
python -c "import dj_database_url; print('Database ENGINE:', dj_database_url.config().get('ENGINE'))"
python manage.py migrate

# 初回の管理者ユーザー作成
if [ "$CREATE_SUPERUSER" = "true" ]; then
    python manage.py createsuperuser --noinput
fi