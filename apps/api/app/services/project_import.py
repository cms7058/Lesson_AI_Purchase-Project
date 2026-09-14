"""Conservative MSP XML preview. No records or notifications are created."""
import xml.etree.ElementTree as ET

from fastapi import HTTPException

from app.domain.projects import ProjectInput, ProjectTask


def xml_preview(raw):
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(422, 'XML不能超过2MB')
    try:
        text = raw.decode('utf-8-sig')
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ValueError('禁止DTD和实体声明')
        root = ET.fromstring(text)
        if root.tag.split('}')[-1] != 'Project':
            raise ValueError('不是Microsoft Project XML')
        for node in root.iter():
            node.tag = node.tag.split('}')[-1]
        get = lambda node, key, default='': node.findtext(key, default=default)
        tasks = []
        warnings = ['仅形成草稿，不发布、不通知；资源、工作日历、基线和高级约束尚未导入，请对照原文件复核。']
        parents = {}
        nodes = root.findall('./Tasks/Task')
        if len(nodes) > 501:
            raise ValueError('最多导入500个任务')
        ids = {get(n, 'UID') for n in nodes if get(n, 'UID') != '0'}
        for node in nodes:
            uid = get(node, 'UID')
            if uid == '0':
                continue
            level = int(get(node, 'OutlineLevel', '1'))
            parent = parents.get(level-1)
            parents = {k: v for k, v in parents.items() if k < level}
            parents[level] = uid
            predecessors = []
            for link in node.findall('PredecessorLink'):
                other = get(link, 'PredecessorUID')
                if other in ids:
                    predecessors.append(other)
                if get(link, 'Type', '1') != '1' or get(link, 'LinkLag', '0') != '0':
                    warnings.append(f'任务 {uid} 有非完成-开始依赖或时滞；仅保留前置编号，需要人工完善。')
            tasks.append(ProjectTask(id=uid, name=get(node, 'Name') or '未命名任务', parent_id=parent,
                kind='milestone' if get(node, 'Milestone') == '1' else 'work_package' if get(node, 'Summary') == '1' else 'task',
                start=get(node, 'Start')[:10] or None, finish=get(node, 'Finish')[:10] or None,
                progress=int(get(node, 'PercentComplete', '0')), predecessors=predecessors,
                source=f'Microsoft Project XML · UID={uid}'))
        if not tasks:
            raise ValueError('没有可导入任务')
        draft = ProjectInput(code='IMPORT-DRAFT', name=get(root, 'Name') or '导入项目', tasks=tasks)
        return {'draft': draft.model_dump(mode='json'), 'warnings': warnings}
    except (ValueError, ET.ParseError, UnicodeDecodeError) as exc:
        raise HTTPException(422, '导入校验失败：'+str(exc)[:250]) from None
