#!/usr/bin/env bash
set -o errexit

python -m pip install --only-binary=pydantic-core -r requirements.txt
python manage.py migrate

# 初回の管理者ユーザー作成
if [ "$CREATE_SUPERUSER" = "true" ]; then
    python manage.py createsuperuser --noinput
fi