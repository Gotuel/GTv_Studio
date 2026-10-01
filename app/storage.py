from urllib.parse import quote

import requests
from flask import current_app


def _object_url(object_path):
    base = current_app.config["SUPABASE_URL"].rstrip("/")
    bucket = quote(current_app.config["SUPABASE_STORAGE_BUCKET"], safe="")
    path = quote(object_path, safe="/")
    return f"{base}/storage/v1/object/{bucket}/{path}"


def _authenticated_object_url(object_path):
    base = current_app.config["SUPABASE_URL"].rstrip("/")
    bucket = quote(current_app.config["SUPABASE_STORAGE_BUCKET"], safe="")
    path = quote(object_path, safe="/")
    return f"{base}/storage/v1/object/authenticated/{bucket}/{path}"


def _headers():
    key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }


def upload_audio(object_path, content, overwrite=False):
    headers = _headers()
    headers["Content-Type"] = "audio/mpeg"
    headers["x-upsert"] = "true" if overwrite else "false"
    response = requests.post(
        _object_url(object_path),
        headers=headers,
        data=content,
        timeout=60,
    )
    response.raise_for_status()


def download_audio(object_path):
    response = requests.get(
        _authenticated_object_url(object_path),
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.content
