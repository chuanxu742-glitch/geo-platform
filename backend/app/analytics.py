import math
import os
import re
from datetime import datetime, timezone
from sqlalchemy import select, func
from fastapi import HTTPException
from .models import Answer, Analysis, AnalysisRun, Batch, Diagnosis, Project
from .common import rows, serialize
from .integrations import model_configured, semantic_analysis


def evidence_matches(text, names):
    matches = []
    seen = set()
    for name in dict.fromkeys(names):
        if not name.strip():
            continue
        # ASCII names must not match inside other alphanumeric words; CJK names
        # legitimately occur without whitespace in prose.
        pattern = re.escape(name)
        if name[0].isascii() and name[0].isalnum():
            pattern = r"(?<![A-Za-z0-9_])" + pattern
        if name[-1].isascii() and name[-1].isalnum():
            pattern += r"(?![A-Za-z0-9_])"
        for match in re.finditer(pattern, text, re.IGNORECASE):
            span = (match.start(), match.end())
            if span not in seen:
                seen.add(span)
                matches.append({"start": span[0], "end": span[1], "quote": match.group(), "matched_name": name})
    return sorted(matches, key=lambda item: (item["start"], item["end"]))


def explicit_rank(text, brand_evidence):
    numbered = list(re.finditer(r"(?m)^\s*(?:#{1,6}\s*)?(\d{1,3})[.、)．]\s*([^\n]+)", text))
    if len(numbered) < 2:
        return None, None
    ranks = []
    for item in numbered:
        rank = int(item.group(1))
        if rank > 0 and any(item.start(2) <= e["start"] < item.end(2) for e in brand_evidence):
            ranks.append((rank, {"start": item.start(), "end": item.end(), "quote": item.group()}))
    return ranks[0] if len(ranks) == 1 else (None, None)


def parse_time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def active_facts(facts, at):
    at = parse_time(at)
    return [fact for fact in facts if (not fact.get("valid_from") or parse_time(fact["valid_from"]) <= at) and (not fact.get("valid_to") or at < parse_time(fact["valid_to"]))]


def analyze_batch(db, batch, use_model, use_current_aliases=False):
    if use_model and not model_configured():
        raise HTTPException(503, "模型未配置；可选择规则分析，推荐语义和事实判定保留unknown")
    snapshot = {**batch.snapshot}
    if use_current_aliases:
        snapshot["aliases"] = list(db.get(Project, batch.project_id).aliases)
    run = AnalysisRun(batch_id=batch.id, input_snapshot={**snapshot, "alias_policy": "current_project" if use_current_aliases else "batch_snapshot", "analyzer_version": "rules-1", "model": os.getenv("OPENAI_MODEL") if use_model else None}, model_status="completed" if use_model else "not_configured" if not model_configured() else "not_requested")
    db.add(run)
    db.flush()
    answers = rows(db, Answer, batch_id=batch.id)
    for answer in answers:
        version = (db.scalar(select(func.max(Analysis.version)).where(Analysis.answer_id == answer.id)) or 0) + 1
        valid = answer.validity == "valid"
        brand_evidence = evidence_matches(answer.text, [snapshot["brand"], *snapshot["aliases"]]) if valid else []
        competitor_evidence = [{"name": c["name"], "evidence": evidence_matches(answer.text, [c["name"], *c["aliases"]])} for c in snapshot["competitors"]] if valid else []
        semantic = {"recommendation": "unknown", "recommendation_evidence": [], "factual_findings": [], "competitor_recommendations": [{"name": c["name"], "recommendation": "unknown", "evidence": []} for c in snapshot["competitors"]]}
        if use_model and valid:
            semantic = semantic_analysis(answer.text, snapshot, active_facts(snapshot["facts"], answer.observed_at or answer.created_at))
            existing = {c["name"] for c in semantic["competitor_recommendations"]}
            semantic["competitor_recommendations"].extend({"name": c["name"], "recommendation": "unknown", "evidence": []} for c in snapshot["competitors"] if c["name"] not in existing)
        list_evidence = semantic.pop("recommendation_list_evidence", [])
        rank, rank_evidence = explicit_rank(answer.text, brand_evidence) if valid and semantic["recommendation"] == "recommended" and list_evidence else (None, None)
        if rank_evidence and not any(e["start"] <= rank_evidence["start"] and e["end"] >= rank_evidence["end"] for e in list_evidence):
            rank, rank_evidence = None, None
        if rank_evidence and not any(e["start"] < rank_evidence["end"] and e["end"] > rank_evidence["start"] for e in semantic["recommendation_evidence"]):
            rank, rank_evidence = None, None
        if rank_evidence:
            rank_evidence["recommendation_list_evidence"] = list_evidence
        findings = semantic["factual_findings"]
        factual = "inconsistent" if any(f["status"] == "inconsistent" for f in findings) else "consistent" if findings else "unknown"
        db.add(Analysis(answer_id=answer.id, run_id=run.id, version=version, brand_mentioned=bool(brand_evidence) if valid else None,
            brand_evidence=brand_evidence, competitor_evidence=competitor_evidence, rank=rank, rank_evidence=rank_evidence,
            factual_status=factual, model_status=run.model_status if valid else "answer_not_valid", **semantic))
    db.commit()
    return {"analysis_run_id": run.id, "answers_analyzed": len(answers), "model_status": run.model_status}


def latest_analyses(db, answer_ids):
    if not answer_ids:
        return {}
    latest = select(Analysis.answer_id, func.max(Analysis.version).label("version")).where(Analysis.answer_id.in_(answer_ids)).group_by(Analysis.answer_id).subquery()
    return {item.answer_id: item for item in db.scalars(select(Analysis).join(latest, (Analysis.answer_id == latest.c.answer_id) & (Analysis.version == latest.c.version)))}


def metric(numerator, denominator, all_ids):
    known = set(denominator)
    return {"answer_ids": numerator, "denominator_answer_ids": denominator, "unknown_answer_ids": [i for i in all_ids if i not in known]}


def group_metrics(entries, branded):
    ids = [a.id for a, _, _ in entries]
    valid = [a.id for a, _, _ in entries if a.validity == "valid"]
    analyzed = [a.id for a, analysis, _ in entries if analysis is not None]
    mentions = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.brand_mentioned is True]
    mention_den = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.brand_mentioned is not None]
    recommended = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.recommendation == "recommended"]
    rec_den = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.recommendation != "unknown"]
    negative = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.recommendation == "not_recommended"]
    neutral = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.recommendation == "neutral"]
    facts = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.factual_status == "inconsistent"]
    fact_den = [a.id for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.factual_status != "unknown"]
    ranked = [(a.id, analysis.rank) for a, analysis, _ in entries if a.validity == "valid" and analysis and analysis.rank is not None]
    source_known = [a.id for a, _, _ in entries if a.validity == "valid" and a.source_state != "unknown"]
    source_present = [a.id for a, _, _ in entries if a.validity == "valid" and a.source_state == "present"]
    competitors = []
    names = sorted({c["name"] for _, _, snapshot in entries for c in snapshot["competitors"]})
    for name in names:
        eligible = [(a, next((c for c in analysis.competitor_recommendations if c["name"] == name), None) if analysis else None) for a, analysis, snapshot in entries if any(c["name"] == name for c in snapshot["competitors"])]
        all_competitor_ids = [a.id for a, _ in eligible]
        den = [a.id for a, c in eligible if a.validity == "valid" and c and c["recommendation"] != "unknown"]
        num = [a.id for a, c in eligible if a.validity == "valid" and c and c["recommendation"] == "recommended"]
        competitors.append({"name": name, "sample_count": len(eligible), "recommended_count": len(num), "denominator": len(den), "unknown_count": len(eligible) - len(den), "recommendation_rate": len(num) / len(den) if den else None, **metric(num, den, all_competitor_ids)})
    return {"branded": branded, "sample_count": len(ids), "valid_count": len(valid), "invalid_count": sum(a.validity == "invalid" for a, _, _ in entries), "unknown_count": sum(a.validity == "unknown" for a, _, _ in entries), "analyzed_count": len(analyzed),
        "brand_mentions": len(mentions), "mention_denominator": len(mention_den), "mention_unknown_count": len(ids) - len(mention_den), "mention_rate": len(mentions) / len(mention_den) if mention_den else None,
        "recommended_count": len(recommended), "not_recommended_count": len(negative), "neutral_count": len(neutral), "recommendation_denominator": len(rec_den), "recommendation_unknown_count": len(ids) - len(rec_den), "recommendation_rate": len(recommended) / len(rec_den) if rec_den else None,
        "factual_error_count": len(facts), "factual_denominator": len(fact_den), "factual_unknown_count": len(ids) - len(fact_den), "factual_error_rate": len(facts) / len(fact_den) if fact_den else None,
        "rank_mean": sum(rank for _, rank in ranked) / len(ranked) if ranked else None, "rank_denominator": len(ranked), "source_known_count": len(source_known), "source_unknown_count": len(ids) - len(source_known), "answer_ids": ids, "competitors": competitors,
        "metrics": {"brand_mentions": metric(mentions, mention_den, ids), "recommendation": metric(recommended, rec_den, ids), "not_recommended": metric(negative, rec_den, ids), "neutral": metric(neutral, rec_den, ids), "factual": metric(facts, fact_den, ids), "rank": metric([i for i, _ in ranked], [i for i, _ in ranked], ids), "sources": metric(source_present, source_known, ids)}}


def overview(db, project_id, batch_id=None, platform=None, region=None, intent=None, question_ids=None, group_by=None):
    batches = rows(db, Batch, project_id=project_id)
    if batch_id is not None:
        batches = [b for b in batches if b.id == batch_id]
        if not batches:
            raise HTTPException(404, "批次不属于该项目")
    lookup = {b.id: b for b in batches}
    answers = list(db.scalars(select(Answer).where(Answer.batch_id.in_(lookup)).order_by(Answer.id))) if lookup else []
    analyses = latest_analyses(db, [a.id for a in answers])
    questions = {q["id"]: q for b in batches for q in b.snapshot["questions"]}
    filters = {"platforms": sorted({a.platform for a in answers} | {p for b in batches for p in b.snapshot["sampling"].get("platforms", [])}), "regions": sorted({q["region"] for q in questions.values()}), "intents": sorted({q["intent"] for q in questions.values()})}
    selected = [a for a in answers if (platform is None or a.platform == platform) and (region is None or questions[a.question_version_id]["region"] == region) and (intent is None or questions[a.question_version_id]["intent"] == intent) and (question_ids is None or questions[a.question_version_id]["question_id"] in question_ids)]
    groups = []
    for branded in (False, True):
        entries = [(a, analyses.get(a.id), lookup[a.batch_id].snapshot) for a in selected if questions[a.question_version_id]["branded"] == branded]
        if group_by:
            keys = sorted({a.platform if group_by == "platform" else questions[a.question_version_id][group_by] for a, _, _ in entries})
            for key in keys:
                subgroup = [(a, analysis, snapshot) for a, analysis, snapshot in entries if (a.platform if group_by == "platform" else questions[a.question_version_id][group_by]) == key]
                groups.append({**group_metrics(subgroup, branded), "dimension": group_by, "dimension_value": key})
        else:
            groups.append(group_metrics(entries, branded))
    return {"project_id": project_id, "batch_ids": list(lookup), "filters": filters, "applied_filters": {"platform": platform, "region": region, "intent": intent, "group_by": group_by}, "groups": groups}


def diagnose(db, batch):
    answers = rows(db, Answer, batch_id=batch.id)
    analyses = latest_analyses(db, [a.id for a in answers])
    for answer in answers:
        analysis = analyses.get(answer.id)
        if not analysis or answer.validity != "valid":
            continue
        actual_input = db.get(AnalysisRun, analysis.run_id).input_snapshot
        candidates = []
        if analysis.brand_mentioned is False:
            candidates.append(("brand_absent", "有效回答未提及品牌", {"scope": "entire_answer", "answer_length": len(answer.text), "quote": answer.text, "start": 0, "end": len(answer.text), "brand": actual_input["brand"], "aliases": actual_input["aliases"], "alias_policy": actual_input.get("alias_policy", "batch_snapshot")}, "假设：该问题下的品牌覆盖不足；也可能由采样波动或平台上下文导致，需人工复核"))
            if any(c["evidence"] for c in analysis.competitor_evidence):
                candidates.append(("content_opportunity", "竞品出现而品牌缺席的内容机会", {"competitor_evidence": analysis.competitor_evidence, "question_version_id": answer.question_version_id}, "假设：可补充针对目标意图的有出处内容；竞品被提及并不证明被推荐，也不证明内容导致差距"))
        mismatches = [f for f in analysis.factual_findings if f["status"] == "inconsistent"]
        if mismatches:
            candidates.append(("fact_mismatch", "回答与有效品牌事实不一致", {"findings": mismatches, "facts": [f for f in batch.snapshot["facts"] if f["id"] in {m["fact_id"] for m in mismatches}]}, "假设：来源过期或模型误述；也可能是事实范围理解差异，需核对出处与有效时间"))
        for kind, title, evidence, hypothesis in candidates:
            exists = db.scalar(select(Diagnosis).where(Diagnosis.answer_id == answer.id, Diagnosis.analysis_id == analysis.id, Diagnosis.kind == kind))
            if not exists:
                db.add(Diagnosis(project_id=batch.project_id, batch_id=batch.id, answer_id=answer.id, analysis_id=analysis.id, kind=kind, title=title, evidence=evidence, hypothesis=hypothesis))
    db.commit()
    return [serialize(item) for item in rows(db, Diagnosis, batch_id=batch.id)]


def wilson(success, total):
    if not total:
        return None
    z = 1.96
    p = success / total
    divisor = 1 + z * z / total
    center = (p + z * z / (2 * total)) / divisor
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / divisor
    return [max(0, center - margin), min(1, center + margin)]


def compare_groups(baseline_groups, retest_groups):
    output = []
    for baseline, retest in zip(baseline_groups, retest_groups):
        intervals = {}
        sample_warnings = {}
        for name, numerator, denominator in (("mention", "brand_mentions", "mention_denominator"), ("recommendation", "recommended_count", "recommendation_denominator"), ("factual_error", "factual_error_count", "factual_denominator")):
            left = wilson(baseline[numerator], baseline[denominator])
            right = wilson(retest[numerator], retest[denominator])
            intervals[f"{name}_difference_interval"] = [right[0] - left[1], right[1] - left[0]] if left and right else None
            sample_warnings[name] = min(baseline[denominator], retest[denominator]) < 30
        delta = lambda field: retest[field] - baseline[field] if retest[field] is not None and baseline[field] is not None else None
        output.append({"branded": baseline["branded"], "baseline": baseline, "retest": retest, "mention_rate_delta": delta("mention_rate"), "recommendation_rate_delta": delta("recommendation_rate"), "factual_error_rate_delta": delta("factual_error_rate"), "uncertainty": {"method": "95% Wilson边界的保守差值范围（非差值置信度保证）", **intervals, "sample_insufficient": sample_warnings["mention"], "metric_sample_warnings": sample_warnings, "caveat": "描述性比较；按非配对、独立样本解释，重复平台/问题可能相关；少于30个已知样本仅为小样本警告，不是有效性阈值；不可据此宣称因果"}})
    return output
