from __future__ import annotations

from collections import defaultdict, deque

from ai_doc.domain.documents import Document, DocumentationSnapshot


class DocumentGraph:
    def __init__(self, snapshot: DocumentationSnapshot) -> None:
        self._documents = snapshot.by_relative_path()
        outgoing: dict[str, set[str]] = defaultdict(set)
        incoming: dict[str, set[str]] = defaultdict(set)
        for document in snapshot.documents:
            for link in document.links:
                if link.is_local_markdown and link.resolved_path in self._documents:
                    outgoing[document.relative_path].add(link.resolved_path or "")
                    incoming[link.resolved_path or ""].add(document.relative_path)
        self._outgoing = outgoing
        self._incoming = incoming

    def outgoing(self, document: Document | str) -> list[str]:
        key = document.relative_path if isinstance(document, Document) else document
        return sorted(self._outgoing.get(key, set()))

    def incoming(self, document: Document | str) -> list[str]:
        key = document.relative_path if isinstance(document, Document) else document
        return sorted(self._incoming.get(key, set()))

    def reachable_from(self, document: Document | str) -> list[str]:
        start = document.relative_path if isinstance(document, Document) else document
        seen: set[str] = set()
        queue: deque[str] = deque(self._outgoing.get(start, set()))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(self._outgoing.get(current, set()) - seen)
        return sorted(seen)
