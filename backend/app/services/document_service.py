import csv
from typing import List

from app.core.config import settings
from app.schemas.schemas import Document


def get_documents() -> List[Document]:
    documents: List[Document] = []
    with open(settings.documents_csv_path, encoding="utf-8-sig", newline="") as f:
        for record in csv.DictReader(f):
            documents.append(Document(
                document_id=record["document_id"],
                title=record["title"],
                published_date=record["published_at"],
                ext=record["ext"]
            ))
    return documents
