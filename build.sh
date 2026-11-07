#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py migrate

# 初回の管理者ユーザー作成
if [ "$CREATE_SUPERUSER" = "true" ]; then
    python manage.py createsuperuser --noinput
fi