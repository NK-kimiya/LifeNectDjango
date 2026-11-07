#!/usr/bin/env bash
set -o errexit

python --version && python -m pip install -v -r requirements.txt
python manage.py migrate

# 初回の管理者ユーザー作成
if [ "$CREATE_SUPERUSER" = "true" ]; then
    python manage.py createsuperuser --noinput
fi