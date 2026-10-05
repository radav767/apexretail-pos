from math import ceil
from typing import Any, Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int
    summary: dict[str, Any] | None = None


def page_response(items, page: int, page_size: int, total: int, *, summary=None):
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
        "summary": summary,
    }
