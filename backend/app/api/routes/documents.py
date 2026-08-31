from fastapi import APIRouter
from typing import List

from app.schemas.schemas import BaseResponse, Document, success
from app.services.document_service import get_documents

router = APIRouter()

@router.get("/documents", response_model=BaseResponse[List[Document]])
def list_documents():
    return success(data=get_documents())