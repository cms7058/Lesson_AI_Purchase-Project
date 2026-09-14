import re

from sqlalchemy import select

from app.domain.knowledge import KnowledgeDocumentRecord


def retrieve_knowledge(db, message: str, domain: str, limit: int = 3) -> list[dict]:
    rows = db.scalars(
        select(KnowledgeDocumentRecord).where(
            KnowledgeDocumentRecord.status == "active",
            KnowledgeDocumentRecord.domain.in_((domain, "shared")),
        )
    ).all()
    terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_]{2,}", message)}
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", message):
        for size in (2, 3, 4):
            terms.update(run[index : index + size] for index in range(len(run) - size + 1))
    scored = []
    for row in rows:
        searchable = f"{row.title} {row.tags} {row.content}".lower()
        score = sum((3 if term in row.title.lower() else 1) * searchable.count(term) for term in terms)
        if score:
            pos = min((searchable.find(term) for term in terms if term in searchable), default=0)
            start = max(0, pos - 80)
            snippet = row.content[start : start + 360].replace("\n", " ").strip()
            scored.append((score, row.updated_at, {"id": row.id, "title": row.title, "source": row.source_name, "domain": row.domain, "snippet": snippet}))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:limit]]
