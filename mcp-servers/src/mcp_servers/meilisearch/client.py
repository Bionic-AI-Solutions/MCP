"""
MeiliSearch Client Wrapper

Provides async-friendly wrapper around MeiliSearch Python client.
"""

from typing import Dict, List, Any, Optional
from meilisearch import Client as MeiliSearchClient


class MeiliSearchClientWrapper:
    """Wrapper around MeiliSearch client for async operations."""

    def __init__(self, client: MeiliSearchClient):
        self.client = client

    # Index Management
    def list_indexes(self) -> List[Dict[str, Any]]:
        """List all indexes."""
        indexes = self.client.get_indexes()
        return [
            {
                "uid": idx.uid,
                "primary_key": idx.primary_key,
                "created_at": idx.created_at,
                "updated_at": idx.updated_at,
            }
            for idx in indexes["results"]
        ]

    def get_index(self, index_uid: str) -> Dict[str, Any]:
        """Get index information."""
        index = self.client.index(index_uid)
        stats = index.get_stats()
        return {
            "uid": index_uid,
            "primary_key": index.primary_key,
            "created_at": index.created_at,
            "updated_at": index.updated_at,
            "number_of_documents": stats.get("number_of_documents", 0),
            "is_indexing": stats.get("is_indexing", False),
        }

    def create_index(self, index_uid: str, primary_key: Optional[str] = None) -> Dict[str, Any]:
        """Create a new index."""
        index = self.client.create_index(index_uid, {"primaryKey": primary_key} if primary_key else None)
        return {
            "uid": index.uid,
            "primary_key": index.primary_key,
            "created_at": index.created_at,
            "updated_at": index.updated_at,
        }

    def delete_index(self, index_uid: str) -> bool:
        """Delete an index."""
        self.client.delete_index(index_uid)
        return True

    # Document Operations
    def add_documents(
        self,
        index_uid: str,
        documents: List[Dict[str, Any]],
        primary_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add documents to an index."""
        index = self.client.index(index_uid)
        task = index.add_documents(documents, primary_key)
        return {
            "task_uid": task["taskUid"],
            "index_uid": task["indexUid"],
            "status": task["status"],
            "type": task["type"],
        }

    def update_documents(
        self,
        index_uid: str,
        documents: List[Dict[str, Any]],
        primary_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update documents in an index."""
        index = self.client.index(index_uid)
        task = index.update_documents(documents, primary_key)
        return {
            "task_uid": task["taskUid"],
            "index_uid": task["indexUid"],
            "status": task["status"],
            "type": task["type"],
        }

    def delete_documents(self, index_uid: str, document_ids: List[str]) -> Dict[str, Any]:
        """Delete documents from an index."""
        index = self.client.index(index_uid)
        task = index.delete_documents(document_ids)
        return {
            "task_uid": task["taskUid"],
            "index_uid": task["indexUid"],
            "status": task["status"],
            "type": task["type"],
        }

    def delete_all_documents(self, index_uid: str) -> Dict[str, Any]:
        """Delete all documents from an index."""
        index = self.client.index(index_uid)
        task = index.delete_all_documents()
        return {
            "task_uid": task["taskUid"],
            "index_uid": task["indexUid"],
            "status": task["status"],
            "type": task["type"],
        }

    def get_document(self, index_uid: str, document_id: str) -> Dict[str, Any]:
        """Get a single document by ID."""
        index = self.client.index(index_uid)
        return index.get_document(document_id)

    def get_documents(
        self,
        index_uid: str,
        limit: int = 20,
        offset: int = 0,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get documents from an index."""
        index = self.client.index(index_uid)
        params = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields
        return index.get_documents(params)

    # Search Operations
    def search(
        self,
        index_uid: str,
        query: str,
        limit: int = 20,
        offset: int = 0,
        filter: Optional[str] = None,
        sort: Optional[List[str]] = None,
        attributes_to_retrieve: Optional[List[str]] = None,
        attributes_to_crop: Optional[List[str]] = None,
        crop_length: int = 200,
        attributes_to_highlight: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Search documents in an index."""
        index = self.client.index(index_uid)
        search_params = {
            "limit": limit,
            "offset": offset,
        }
        if filter:
            search_params["filter"] = filter
        if sort:
            search_params["sort"] = sort
        if attributes_to_retrieve:
            search_params["attributesToRetrieve"] = attributes_to_retrieve
        if attributes_to_crop:
            search_params["attributesToCrop"] = attributes_to_crop
        search_params["cropLength"] = crop_length
        if attributes_to_highlight:
            search_params["attributesToHighlight"] = attributes_to_highlight

        return index.search(query, search_params)

    # Settings Operations
    def get_settings(self, index_uid: str) -> Dict[str, Any]:
        """Get index settings."""
        index = self.client.index(index_uid)
        return index.get_settings()

    def update_settings(self, index_uid: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update index settings."""
        index = self.client.index(index_uid)
        task = index.update_settings(settings)
        return {
            "task_uid": task["taskUid"],
            "index_uid": task["indexUid"],
            "status": task["status"],
            "type": task["type"],
        }

    def reset_settings(self, index_uid: str) -> Dict[str, Any]:
        """Reset index settings to default."""
        index = self.client.index(index_uid)
        task = index.reset_settings()
        return {
            "task_uid": task["taskUid"],
            "index_uid": task["indexUid"],
            "status": task["status"],
            "type": task["type"],
        }

    # Task Operations
    def get_task(self, index_uid: str, task_uid: int) -> Dict[str, Any]:
        """Get task information."""
        index = self.client.index(index_uid)
        return index.get_task(task_uid)

    def get_tasks(self, index_uid: str) -> Dict[str, Any]:
        """Get all tasks for an index."""
        index = self.client.index(index_uid)
        return index.get_tasks()
