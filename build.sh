#!/usr/bin/env bash
set -o errexit

python -m pip install --only-binary=pydantic-core -r requirements.txt





python manage.py migrate

