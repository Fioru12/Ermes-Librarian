"""Libraries and document inventory endpoints for Ermes Knowledge.

One sub-router per area, each under /api/libraries. Include order is
route-matching order: catalog goes first so `/index-consistency` is matched
before `/{library_id}`, and ask registers `/federated/...` before
`/{library_id}/...` itself.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.auth import _verify_api_key
from api.libraries.ask import _answer_question
from api.libraries.ask import router as _ask_router
from api.libraries.catalog import router as _catalog_router
from api.libraries.common import _unlink_storage_paths, get_library_store
from api.libraries.documents import router as _documents_router
from api.libraries.sources import _reject_source_path_inside_app, _require_library_owner_or_admin
from api.libraries.sources import router as _sources_router
from api.libraries.studio import router as _studio_router

__all__ = [
    "_answer_question",
    "_reject_source_path_inside_app",
    "_require_library_owner_or_admin",
    "_unlink_storage_paths",
    "_verify_api_key",
    "get_library_store",
    "router",
]

router = APIRouter()
for _sub in (_catalog_router, _documents_router, _ask_router, _sources_router, _studio_router):
    router.include_router(_sub)
