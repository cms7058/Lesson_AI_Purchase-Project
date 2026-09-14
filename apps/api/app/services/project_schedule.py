from datetime import timedelta

from fastapi import HTTPException


def shift_tasks(tasks, task_id, days):
    by_id = {t.id: t for t in tasks}
    if task_id not in by_id:
        raise HTTPException(404, '任务不存在')
    affected = {task_id}
    while True:
        added = {t.id for t in tasks if t.parent_id in affected or any(p in affected for p in t.predecessors)}
        if added <= affected:
            break
        affected |= added
    result = [t.model_copy(deep=True) for t in tasks]
    for t in result:
        if t.id in affected:
            if not t.start or not t.finish:
                raise HTTPException(409, '联动任务存在未填写日期，请先完善任务日期')
            if t.progress == 100:
                raise HTTPException(409, '联动范围包含已完成任务，请先通过计划变更处理')
            t.start += timedelta(days=days)
            t.finish += timedelta(days=days)
    shifted = {t.id: t for t in result}
    for t in result:
        if t.id in affected:
            for predecessor in t.predecessors:
                p = shifted[predecessor]
                if not p.finish or t.start <= p.finish:
                    raise HTTPException(409, f'任务“{t.name}”必须在前置任务完成后的下一日或更晚开始')
    # Roll work-package bounds up from direct children, bottom-up.
    for _ in range(len(result)):
        changed = False
        for parent in result:
            children = [t for t in result if t.parent_id == parent.id]
            if parent.kind == 'work_package' and children and all(t.start and t.finish for t in children):
                start, finish = min(t.start for t in children), max(t.finish for t in children)
                if (parent.start, parent.finish) != (start, finish):
                    parent.start, parent.finish = start, finish
                    changed = True
        if not changed:
            break
    return {'tasks': [t.model_dump(mode='json') for t in result], 'moved': len(affected), 'days': days}
