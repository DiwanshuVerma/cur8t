#!/usr/bin/env python3
"""
Simplified FastAPI app for VS Code extension development
This version removes database dependencies and focuses on basic functionality
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Cur8t Extension API",
    description="API for VS Code extension integration",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class VSCodeExtension(BaseModel):
    id: str
    version: str
    description: str
    name: str
    publisher: str


class ExportCollectionRequest(BaseModel):
    extensions: List[Dict[str, str]]
    collectionName: Optional[str] = None
    description: Optional[str] = None


class ExportCollectionResponse(BaseModel):
    collectionId: str
    collectionUrl: str
    message: str


# In-memory storage for development
collections_db = {}
api_keys_db = {}


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Cur8t Extension API is running"}


# Test authentication endpoint
@app.get("/api/test-auth")
async def test_auth(authorization: Optional[str] = Header(None)):
    """Test authentication endpoint"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    api_key = authorization[7:]  # Remove "Bearer " prefix

    # For development, accept any API key that starts with "dev-"
    if api_key.startswith("dev-"):
        return {"status": "authenticated", "api_key": api_key[:8] + "..."}

    raise HTTPException(status_code=401, detail="Invalid API key")


# Export VS Code extensions endpoint
@app.post("/api/export-collection", response_model=ExportCollectionResponse)
async def export_vscode_extensions(
    request: Request,
    export_data: ExportCollectionRequest,
    authorization: Optional[str] = Header(None),
) -> ExportCollectionResponse:
    """Export VS Code extensions to a Cur8t collection"""

    # Validate input data
    if not export_data.extensions:
        raise HTTPException(status_code=400, detail="No extensions provided")
    if len(export_data.extensions) > 1000:  # Reasonable limit
        raise HTTPException(status_code=400, detail="Too many extensions (max: 1000)")

    logger.info("🚀 VS CODE EXPORT - Endpoint called")
    logger.info(
        f"🚀 VS CODE EXPORT - Number of extensions: {len(export_data.extensions)}"
    )

    # Validate authorization
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    api_key = authorization[7:]  # Remove "Bearer " prefix

    # For development, accept any API key that starts with "dev-"
    if not api_key.startswith("dev-"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        # Create collection name and description
        collection_name = (
            export_data.collectionName
            or f"VS Code Extensions - {datetime.now().strftime('%Y-%m-%d')}"
        )
        collection_description = (
            export_data.description
            or f"Exported {len(export_data.extensions)} VS Code extensions on {datetime.now().strftime('%Y-%m-%d')}"
        )

        # Create new collection
        collection_id = str(uuid.uuid4())

        # Store collection in memory
        collections_db[collection_id] = {
            "id": collection_id,
            "title": collection_name,
            "description": collection_description,
            "visibility": "private",
            "user_id": "dev-user",
            "total_links": len(export_data.extensions),
            "created_at": datetime.now().isoformat(),
            "extensions": export_data.extensions,
        }

        # Create collection URL for the response
        collection_view_url = f"https://cur8t.com/collection/{collection_id}"

        logger.info(
            f"🚀 VS CODE EXPORT - Successfully created collection with {len(export_data.extensions)} extension links"
        )

        return ExportCollectionResponse(
            collectionId=collection_id,
            collectionUrl=collection_view_url,
            message=f"Successfully exported {len(export_data.extensions)} VS Code extensions to Cur8t collection",
        )

    except Exception as e:
        logger.error(f"❌ Unexpected error in VS Code export: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to export VS Code extensions: {str(e)}"
        )


# Get user collections endpoint
@app.get("/api/user/collections")
async def get_user_collections(
    request: Request, authorization: Optional[str] = Header(None)
) -> Dict[str, List[Dict[str, Any]]]:
    """Get user's collections for VS Code extension"""
    logger.info("📁 USER COLLECTIONS - Endpoint called")

    # Validate authorization
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    api_key = authorization[7:]  # Remove "Bearer " prefix

    # For development, accept any API key that starts with "dev-"
    if not api_key.startswith("dev-"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        # Get all collections from memory
        collections = []
        for collection_id, collection_data in collections_db.items():
            collection = {
                "id": collection_id,
                "name": collection_data["title"],
                "description": collection_data["description"],
                "createdAt": collection_data["created_at"],
                "extensionCount": collection_data["total_links"],
            }
            collections.append(collection)

        return {"collections": collections}

    except Exception as e:
        logger.error(f"❌ Unexpected error in user collections: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch user collections: {str(e)}"
        )


# Get specific collection endpoint
@app.get("/api/collections/{collection_id}")
async def get_collection_by_id(
    collection_id: str, authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Get specific collection details"""
    logger.info(f"📁 COLLECTION DETAILS - Endpoint called for ID: {collection_id}")

    # Validate authorization
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    api_key = authorization[7:]  # Remove "Bearer " prefix

    # For development, accept any API key that starts with "dev-"
    if not api_key.startswith("dev-"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        # Get collection from memory
        if collection_id not in collections_db:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection_data = collections_db[collection_id]
        collection = {
            "id": collection_id,
            "name": collection_data["title"],
            "description": collection_data["description"],
            "createdAt": collection_data["created_at"],
            "extensionCount": collection_data["total_links"],
        }

        return collection

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in collection details: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch collection details: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
