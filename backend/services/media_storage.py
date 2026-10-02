"""Media persistence boundary with a local development adapter."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException

APP_ROOT=Path(__file__).resolve().parent.parent
STORAGE_BACKEND=os.getenv("MEDIA_STORAGE","local").strip().lower()
MEDIA_DIR=Path(os.getenv("MEDIA_LOCAL_DIR",str(APP_ROOT/"uploads"))).expanduser().resolve()
MEDIA_DIR.mkdir(parents=True,exist_ok=True)

def _safe_name(filename):
    name=Path(filename).name
    if not name or not re.fullmatch(r"[A-Za-z0-9_.-]+",name):
        raise HTTPException(status_code=400,detail="Invalid media filename.")
    return name

def get_media_url(filename):
    name=_safe_name(filename)
    if STORAGE_BACKEND=="local": return f"/uploads/{name}"
    raise HTTPException(status_code=500,detail="Configured media URL adapter is unavailable.")

def save_media(data,filename,content_type="application/octet-stream"):
    if STORAGE_BACKEND!="local":
        raise HTTPException(status_code=500,detail="Configured media storage adapter is unavailable.")
    if not data: raise HTTPException(status_code=500,detail="Cannot save empty media.")
    name=_safe_name(filename); (MEDIA_DIR/name).write_bytes(data)
    return get_media_url(name)

def resolve_local_media(media_url):
    if STORAGE_BACKEND!="local":
        raise HTTPException(status_code=400,detail="This media item is not stored by the local adapter.")
    if not isinstance(media_url,str): raise HTTPException(status_code=400,detail="Media URL must reference /uploads/.")
    parsed=urlparse(media_url); media_path=parsed.path if parsed.scheme in {"http","https"} else media_url
    if not media_path.startswith("/uploads/"):
        raise HTTPException(status_code=400,detail="Media URL must reference /uploads/.")
    name=_safe_name(media_path.removeprefix("/uploads/")); path=(MEDIA_DIR/name).resolve()
    if path.parent!=MEDIA_DIR: raise HTTPException(status_code=400,detail="Invalid media reference.")
    if not path.is_file(): raise HTTPException(status_code=404,detail="Media file was not found.")
    return path
