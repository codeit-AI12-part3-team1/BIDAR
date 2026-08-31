import json
from typing import List

from app.core.config import settings
from app.schemas.schemas import Document


def get_documents() -> List[Document]:
    documents: List[Document] = []
    with open(settings.documents_jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            documents.append(Document(
                file_name=record["source_filename_nfc"],
                document_id=record["document_id"],
            ))
    return documents
