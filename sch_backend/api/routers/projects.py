from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
import logfire

from sch_backend.api.dependencies import get_current_user
from sch_backend.models.domain import Project
from sch_backend.repositories.database_repository import DatabaseRepository

router = APIRouter(tags=["projects"])


@router.get("", response_model=List[Project])
@logfire.instrument("api.projects.list_projects")
async def list_projects(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Project]:
    """
    List all projects the current user has access to.
    """
    repo = DatabaseRepository()
    user_email = current_user["email"]

    projects = await repo.get_user_projects(user_email)
    return projects
