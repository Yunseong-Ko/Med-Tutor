def reconcile_generation_queue_items(
    items,
    async_job,
    add_questions_fn,
    drop_payload_fn,
    now_iso,
    default_quality_filter=True,
    default_min_length=30,
    mode_mcq="mcq",
):
    queue_items = items if isinstance(items, list) else []
    notices = []
    if not isinstance(async_job, dict):
        return queue_items, None, notices

    queue_id = str(async_job.get("queue_id") or "")
    target_idx = -1
    for idx, item in enumerate(queue_items):
        if str(item.get("id")) == queue_id:
            target_idx = idx
            break
    if target_idx < 0:
        return queue_items, None, notices

    target = dict(queue_items[target_idx])
    target["completed_at"] = str(now_iso or "")
    status = str(async_job.get("status") or "")

    if status == "done":
        result = async_job.get("result") or []
        if result and isinstance(result, list):
            saved_count = add_questions_fn(
                result,
                target.get("mode", mode_mcq),
                target.get("subject", "General"),
                target.get("unit", "미분류"),
                quality_filter=bool(target.get("quality_filter", default_quality_filter)),
                min_length=int(target.get("min_length", default_min_length)),
            )
            target["status"] = "done"
            target["result_count"] = len(result)
            target["saved_count"] = int(saved_count)
            dropped = max(0, int(target["result_count"]) - int(saved_count))
            notices.append(
                f"생성 완료: {target.get('source_name', '')} "
                f"(요청 {target['result_count']}개 / 저장 {saved_count}개 / 중복·필터 제외 {dropped}개)"
            )
        else:
            target["status"] = "failed"
            target["error"] = "생성 결과가 비어 있습니다."
            notices.append(f"생성 실패: {target.get('source_name', '')} (결과 없음)")
    elif status == "cancelled":
        target["status"] = "cancelled"
        target["error"] = async_job.get("error", "사용자 취소")
        notices.append(f"작업 취소: {target.get('source_name', '')}")
    else:
        target["status"] = "failed"
        target["error"] = async_job.get("error", "알 수 없는 오류")
        notices.append(f"생성 실패: {target.get('source_name', '')}")

    queue_items[target_idx] = drop_payload_fn(target)
    return queue_items, None, notices
