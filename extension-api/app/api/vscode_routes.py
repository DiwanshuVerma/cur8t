import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, validator

from ..core.database import execute_insert, execute_query_one, execute_query_all
from ..core.subscription import subscription_service
from ..core.utils import limiter
from ..models.schemas import Collection, CreateCollectionResponse, ErrorResponse

# Import get_user_id_from_api_key directly to avoid circular imports
from .routes import get_user_id_from_api_key

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

# VS Code Extension specific schemas
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

class ValidateResponse(BaseModel):
    userId: str
    email: Optional[str] = None
    username: Optional[str] = None

@router.get("/validate", response_model=ValidateResponse)
@limiter.limit("60/minute")
async def validate_api_key(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    logger.info(f"[DEBUG] /validate called with header: {authorization}")

    """Validate API key and return basic user info"""
    
    try:
        user_id = await get_user_id_from_api_key(authorization)
        logger.info(f"[DEBUG] got user_id: {user_id}")

        # Basic user details
        user_query = """
            SELECT id, email, name
            FROM users
            WHERE id = $1
        """
        user = await execute_query_one(user_query, (user_id,))

        logger.info(f"🤝user found: {user}")
        return ValidateResponse(
            userId=str(user_id),
            email=user.get("email") if user else None,
            username=user.get("name") if user else None,
        )
    except HTTPException as e:
        logger.error(f"[HTTPException] {e.detail}")
        raise e         # Re-raise the real status and message
    except Exception as e:
        logger.error(f"[EXCEPTION] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-collection", response_model=ExportCollectionResponse)
@limiter.limit("20/minute")  # Increased limit for better UX
async def export_vscode_extensions(
    request: Request,
    export_data: ExportCollectionRequest,
    authorization: Optional[str] = Header(None),
) -> ExportCollectionResponse:
    # Validate input data
    if not export_data.extensions:
        raise HTTPException(status_code=400, detail="No extensions provided")
    if len(export_data.extensions) > 1000:  # Reasonable limit
        raise HTTPException(status_code=400, detail="Too many extensions (max: 1000)")
    """Export VS Code extensions to a Cur8t collection"""
    logger.info("🚀 VS CODE EXPORT - Endpoint called")
    logger.info(f"🚀 VS CODE EXPORT - Number of extensions: {len(export_data.extensions)}")

    try:
        user_id = await get_user_id_from_api_key(authorization)
        logger.info(f"🚀 VS CODE EXPORT - User ID extracted: {user_id}")

        # Check subscription limits for collection creation
        can_create, error_message, plan_slug = (
            await subscription_service.check_collection_limit(user_id)
        )
        if not can_create:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": error_message,
                    "plan": plan_slug,
                    "upgrade_required": True,
                },
            )

        # Create collection name and description
        collection_name = export_data.collectionName or f"VS Code Extensions - {datetime.now().strftime('%Y-%m-%d')}"
        collection_description = export_data.description or f"Exported {len(export_data.extensions)} VS Code extensions on {datetime.now().strftime('%Y-%m-%d')}"

        # Create new collection
        collection_id = str(uuid.uuid4())
        insert_collection_query = """
            INSERT INTO collections (id, title, description, visibility, user_id, total_links, created_at, updated_at, url)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, title, description, visibility, total_links, created_at
        """

        now = datetime.utcnow()
        # Base URL from configuration or environment variable
        collection_url = os.getenv("VSCODE_MARKETPLACE_URL", "https://marketplace.visualstudio.com")
        
        created_collection = await execute_insert(
            insert_collection_query,
            (
                collection_id,
                collection_name,
                collection_description,
                "public",  # VS Code extensions are public by default
                user_id,
                len(export_data.extensions),
                now,
                now,
                collection_url,
            ),
        )

        if not created_collection:
            raise HTTPException(status_code=500, detail="Failed to create collection")

        # Create links for each extension
        created_links = []
        for extension in export_data.extensions:
            try:
                # Create marketplace URL for the extension
                marketplace_url = f"https://marketplace.visualstudio.com/items?itemName={extension['id']}"
                
                # Create link for the extension
                link_id = str(uuid.uuid4())
                insert_link_query = """
                    INSERT INTO links (id, title, url, link_collection_id, user_id, created_at, updated_at)
                    VALUES ($1::uuid, $2, $3, $4::uuid, $5, $6, $7)
                    RETURNING id, title, url, link_collection_id, user_id, created_at, updated_at
                """

                # Create a descriptive title for the extension
                link_title = f"{extension['name']} v{extension['version']}"
                if extension.get('description'):
                    link_title += f" - {extension['description'][:100]}"

                created_link = await execute_insert(
                    insert_link_query,
                    (
                        link_id,
                        link_title,
                        marketplace_url,
                        collection_id,
                        user_id,
                        now,
                        now,
                    ),
                )

                if created_link:
                    created_links.append(created_link)

            except Exception as e:
                logger.error(f"❌ Failed to create link for extension {extension['id']}: {str(e)}")
                continue

        # Update collection's total links count
        update_collection_query = """
            UPDATE collections 
            SET total_links = $1 
            WHERE id = $2::uuid AND user_id = $3
        """
        await execute_query_one(
            update_collection_query,
            (len(created_links), collection_id, user_id),
        )

        # Create collection URL for the response
        url = os.getenv("CUR8T_WEB_URL") or "https://www.cur8t.com"
        collection_view_url = f"{url}/collection/{collection_id}"

        logger.info(f"🚀 VS CODE EXPORT - Successfully created collection with {len(created_links)} extension links")

        return ExportCollectionResponse(
            collectionId=collection_id,
            collectionUrl=collection_view_url,
            message=f"Successfully exported {len(created_links)} VS Code extensions to Cur8t collection"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in VS Code export: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to export VS Code extensions: {str(e)}"
        )

@router.get("/user/collections")
@limiter.limit("60/minute")
async def get_user_collections(
    request: Request, authorization: Optional[str] = Header(None)
) -> Dict[str, List[Dict[str, Any]]]:
    """Get user's collections for VS Code extension"""
    logger.info("📁 USER COLLECTIONS - Endpoint called")

    try:
        user_id = await get_user_id_from_api_key(authorization)
        logger.info(f"📁 USER COLLECTIONS - User ID extracted: {user_id}")

        # Get user's collections
        collections_query = """
            SELECT id, title, description, visibility, total_links as "totalLinks", created_at as "createdAt"
            FROM collections 
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 20
        """

        collections_result = await execute_query_all(
            collections_query, (user_id,)
        )

        collections = []
        for col_data in collections_result:
            collection = {
                "id": str(col_data["id"]),
                "name": col_data["title"],
                "description": col_data["description"],
                "createdAt": col_data["createdAt"].isoformat(),
                "extensionCount": col_data["totalLinks"],
            }
            collections.append(collection)

        return {"collections": collections}

    except HTTPException as e:
        logger.error(f"❌ HTTP Exception in user collections: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in user collections: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch user collections: {str(e)}"
        )

@router.get("/collections/{collection_id}")
@limiter.limit("60/minute")
async def get_collection_by_id(
    request: Request,
    collection_id: str, authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Get specific collection details"""
    logger.info(f"📁 COLLECTION DETAILS - Endpoint called for ID: {collection_id}")

    try:
        user_id = await get_user_id_from_api_key(authorization)

        # Get collection details
        collection_query = """
            SELECT id, title, description, visibility, total_links as "totalLinks", created_at as "createdAt"
            FROM collections 
            WHERE id = $1::uuid AND user_id = $2
        """

        collection_result = await execute_query_one(
            collection_query, (collection_id, user_id)
        )

        if not collection_result:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection = {
            "id": str(collection_result["id"]),
            "name": collection_result["title"],
            "description": collection_result["description"],
            "createdAt": collection_result["createdAt"].isoformat(),
            "extensionCount": collection_result["totalLinks"],
        }

        return collection

    except HTTPException as e:
        logger.error(f"❌ HTTP Exception in collection details: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in collection details: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch collection details: {str(e)}"
        )
