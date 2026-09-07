"""Bounded, atomic imports of explicitly supplied measurements."""
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .common import require, serialize
from .db import get_db
from .measurement_models import Measurement
from .measurement_schemas import MeasurementImport
from .models import Project


router = APIRouter()
METRICS = ("impressions", "clicks", "leads", "orders")
LIMITATIONS = [
    "数据来自人工导入，来源标签和渠道由导入者声明，未经独立核验。",
    "空值表示未知；无记录或任一记录缺失某指标时，该指标汇总为 null，不按零计算。",
    "同一项目、来源、日期、页面、渠道和查询的记录只保留一份；修订数值会拒绝整批导入，不同来源仍可能重叠。",
    "汇总超过 JavaScript 安全整数上限时返回 null，避免精度丢失。",
    "SEO/GEO 渠道标签不证明因果关系；这些数据不能证明 AI 曝光带来了线索或订单。",
]


@router.post("/projects/{identifier}/measurements/import")
def import_measurements(identifier: int, payload: MeasurementImport, db=Depends(get_db)):
    require(db, Project, identifier)
    candidates = {}
    for row in payload.rows:
        data = {"source_label": payload.source_label, **row.model_dump()}
        identity = {key: value for key, value in data.items() if key not in METRICS}
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode("utf-8")).hexdigest()
        if fingerprint in candidates and candidates[fingerprint] != data:
            raise HTTPException(409, "同一记录在本次导入中包含不同数值，未写入本次数据")
        candidates[fingerprint] = data
    # Chunk to stay below SQLite bind parameter limits even at the import cap.
    fingerprints = list(candidates)
    existing = set()
    for start in range(0, len(fingerprints), 400):
        for record in db.scalars(select(Measurement).where(
            Measurement.project_id == identifier,
            Measurement.fingerprint.in_(fingerprints[start:start + 400]))):
            if any(getattr(record, key) != value for key, value in candidates[record.fingerprint].items()):
                raise HTTPException(409, "已有同一记录包含不同数值，未写入本次数据")
            existing.add(record.fingerprint)
    inserted = len(candidates) - len(existing)
    try:
        db.add_all(Measurement(project_id=identifier, fingerprint=key, **data)
                   for key, data in candidates.items() if key not in existing)
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent import cannot leave a partially imported batch.
        raise HTTPException(409, "导入与并发写入冲突，未写入本次数据；请重试") from None
    except Exception:
        db.rollback()
        raise
    return {"imported": inserted, "duplicates": len(payload.rows) - inserted,
            "source_label": payload.source_label}


@router.get("/projects/{identifier}/measurements")
def measurements(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    records = list(db.scalars(select(Measurement).where(Measurement.project_id == identifier)
                             .order_by(Measurement.date.desc(), Measurement.id.desc())))
    summary = {}
    for metric in METRICS:
        values = [getattr(record, metric) for record in records]
        summary[metric] = sum(values) if values and all(v is not None for v in values) else None
        if summary[metric] is not None and summary[metric] > 9_007_199_254_740_991:
            summary[metric] = None
    return {"rows": [serialize(record) for record in records], "summary": summary,
            "limitations": LIMITATIONS}
