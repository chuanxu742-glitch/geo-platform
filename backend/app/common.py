import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from fastapi import HTTPException
from sqlalchemy import inspect, select
from .schemas import SECRET_KEY


def redact(value):
    if isinstance(value, dict):
        return {str(k): "[已隐藏]" if SECRET_KEY.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, str):
        for key in ("RAZORMIND_API_TOKEN", "OPENAI_API_KEY", "GEO_BACKEND_TOKEN", "WORDPRESS_APPLICATION_PASSWORD", "WORDPRESS_USERNAME"):
            secret = os.getenv(key)
            if secret:
                value = value.replace(secret, "[已隐藏]")
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[已隐藏]", value)
        value = re.sub(r"(?i)((?:api[_-]?key|token|secret|password|cookie|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;}]+", r"\1[已隐藏]", value)
    return value


def serialize(obj):
    return redact({attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs})


def require(db, model, identifier):
    obj = db.get(model, identifier)
    if obj is None:
        raise HTTPException(404, "记录不存在")
    return obj


def owned(db, model, identifiers, project_id):
    result = []
    for identifier in dict.fromkeys(identifiers):
        obj = require(db, model, identifier)
        if obj.project_id != project_id:
            raise HTTPException(422, "引用数据不属于当前项目")
        result.append(obj)
    return result


def rows(db, model, **filters):
    query = select(model)
    for key, value in filters.items():
        query = query.where(getattr(model, key) == value)
    return list(db.scalars(query.order_by(model.id)))
