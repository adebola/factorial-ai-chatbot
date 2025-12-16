from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict, Any
import os
import tempfile
import zipfile
from datetime import datetime

from ..core.database import get_db
from ..services.widget_service import WidgetService
from ..services.dependencies import validate_token, TokenClaims, get_full_tenant_details

router = APIRouter()


@router.get("/widget/generate", response_model=Dict[str, Any])
async def generate_widget_files(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Generate or regenerate widget files for a tenant"""
    
    try:
        # Get full tenant details from the OAuth2 server
        tenant_data = await get_full_tenant_details(claims.tenant_id, claims.access_token)
        
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)
        
        # Determine backend URL for hosted integration
        environment = os.getenv("ENVIRONMENT", "development").lower()
        production_domain = os.getenv("PRODUCTION_DOMAIN", "api.chatcraft.cc")

        if environment == "production" or environment == "prod":
            backend_url = f"https://{production_domain}"
        else:
            backend_url = os.getenv("BACKEND_URL", "http://localhost:8080")

        hosted_widget_url = f"{backend_url}/api/v1/widget/js/{claims.tenant_id}"

        return {
            "message": "Widget files generated successfully",
            "tenant_id": claims.tenant_id,
            "tenant_name": tenant_data.get("name", "Unknown"),
            "files_generated": list(files.keys()),
            "generated_at": datetime.utcnow().isoformat(),
            "download_urls": {
                "javascript": f"/api/v1/widget/chat-widget.js",
                "javascript_minified": f"/api/v1/widget/chat-widget.min.js",
                "css": f"/api/v1/widget/chat-widget.css",
                "demo_html": f"/api/v1/widget/chat-widget.html",
                "integration_guide": f"/api/v1/widget/integration-guide.html",
                "download_all": f"/api/v1/widget/download-all"
            },
            "hosted_widget_url": hosted_widget_url,
            "integration_snippet_hosted": f'<script src="{hosted_widget_url}"></script>',
            "integration_snippet_download": f'<script src="https://your-domain.com/path/to/chat-widget.js"></script>',
            "widget_features": [
                "Real-time AI chat",
                "Mobile responsive design",
                "Custom branding with your colors",
                "Secure WebSocket connection",
                "Dark mode support",
                "Lightweight and fast loading",
                "Minified for optimal performance"
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate widget files: {str(e)}"
        )


@router.get("/widget/chat-widget.js")
async def download_widget_javascript(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Download the chat widget JavaScript file"""
    
    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)
        
        return Response(
            content=files["chat-widget.js"],
            media_type="application/javascript",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-{claims.tenant_id[:8]}.js",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate JavaScript file: {str(e)}"
        )


@router.get("/widget/chat-widget.min.js")
async def download_widget_javascript_minified(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Download the minified chat widget JavaScript file"""

    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)

        return Response(
            content=files["chat-widget.min.js"],
            media_type="application/javascript",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-{claims.tenant_id[:8]}.min.js",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate minified JavaScript file: {str(e)}"
        )


@router.get("/widget/chat-widget.css")
async def download_widget_css(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Download the chat widget CSS file"""

    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)

        return Response(
            content=files["chat-widget.css"],
            media_type="text/css",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-{claims.tenant_id[:8]}.css",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate CSS file: {str(e)}"
        )


@router.get("/widget/chat-widget.html")
async def download_widget_demo(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Download the chat widget demo HTML file"""
    
    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)
        
        return Response(
            content=files["chat-widget.html"],
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-demo-{claims.tenant_id[:8]}.html"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate demo HTML file: {str(e)}"
        )


@router.get("/widget/integration-guide.html")
async def download_integration_guide(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Download the integration guide HTML file"""
    
    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)
        
        return Response(
            content=files["integration-guide.html"],
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=integration-guide-{claims.tenant_id[:8]}.html"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate integration guide: {str(e)}"
        )


@router.get("/widget/download-all")
async def download_all_widget_files(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Download all widget files as a ZIP archive"""
    
    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)
        current_tenant = await get_full_tenant_details(claims.tenant_id, claims.access_token)
        
        # Create a temporary ZIP file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add each file to the ZIP
                for filename, content in files.items():
                    if filename == "integration-guide.html":
                        filename = "README.html"  # Rename for clarity
                    elif filename == "chat-widget.html":
                        filename = "demo.html"  # Rename for clarity
                    
                    zipf.writestr(filename, content)
                
                # Add a simple README.txt
                readme_content = f"""ChatCraft Chat Widget - {current_tenant["name"]}
Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

Files included:
- chat-widget.js: Main widget JavaScript file
- chat-widget.css: Additional CSS styling (optional)
- demo.html: Demo page to test the widget
- README.html: Detailed integration guide

Quick Start:
1. Upload chat-widget.js to your website
2. Add this script tag before </body>:
   <script src="/path/to/chat-widget.js"></script>
3. The chat button will appear in the bottom-right corner

For detailed instructions, open README.html in your browser.

Support: {os.getenv('BACKEND_URL', 'http://localhost:8001')}
"""
                zipf.writestr("README.txt", readme_content)
            
            zip_filename = f"factorial-chat-widget-{current_tenant['name'].lower().replace(' ', '-')}-{claims.tenant_id[:8]}.zip"
            
            return FileResponse(
                temp_zip.name,
                media_type="application/zip",
                filename=zip_filename,
                headers={
                    "Content-Disposition": f"attachment; filename={zip_filename}"
                }
            )
            
    except Exception as e:
        # Clean up the temp file if it exists
        if 'temp_zip' in locals():
            try:
                os.unlink(temp_zip.name)
            except:
                pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create widget package: {str(e)}"
        )


@router.get("/widget/preview")
async def preview_widget(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Preview the chat widget in a demo page"""
    
    try:
        widget_service = WidgetService(db)
        files = await widget_service.generate_widget_files(claims.tenant_id, claims.access_token)
        
        return Response(
            content=files["chat-widget.html"],
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate preview: {str(e)}"
        )


@router.get("/widget/status")
async def get_widget_status(
    claims: TokenClaims = Depends(validate_token),
) -> Dict[str, Any]:
    """Get widget configuration status and information"""

    current_tenant = await get_full_tenant_details(claims.tenant_id, claims.access_token)
    
    return {
        "widget_status": "active",
        "tenant_id": claims.tenant_id,
        "tenant_name": current_tenant["name"],
        "api_key_configured": bool(current_tenant["apiKey"]),
        "backend_url": os.getenv("BACKEND_URL", "http://localhost:8001"),
        "chat_service_url": os.getenv("CHAT_SERVICE_URL", "http://localhost:8000"),
        "widget_colors": {
            "primary": "#5D3EC1",
            "secondary": "#C15D3E", 
            "accent": "#3EC15D"
        },
        "features_enabled": [
            "real_time_chat",
            "mobile_responsive",
            "custom_branding",
            "secure_websocket",
            "dark_mode_support"
        ],
        "last_generated": datetime.utcnow().isoformat(),
        "download_endpoints": {
            "javascript": f"/api/v1/widget/chat-widget.js",
            "css": f"/api/v1/widget/chat-widget.css",
            "demo": f"/api/v1/widget/chat-widget.html",
            "guide": f"/api/v1/widget/integration-guide.html",
            "all_files": f"/api/v1/widget/download-all",
            "preview": f"/api/v1/widget/preview"
        }
    }


@router.get("/widget/js/{tenant_id}")
async def serve_hosted_widget_javascript(
    tenant_id: str,
    minified: bool = True,
    db: Session = Depends(get_db)
):
    """
    Serve hosted minified widget JavaScript for a specific tenant

    This endpoint allows tenants to load the widget directly from the server
    without downloading and hosting it themselves.

    Usage:
        <script src="https://api.chatcraft.cc/api/v1/widget/js/{tenant_id}"></script>

    Query Parameters:
        minified: Whether to serve minified version (default: True)
    """

    try:
        widget_service = WidgetService(db)

        # Generate widget files for the tenant (without authentication for public access)
        # Note: This uses tenant_id directly, so no token validation required
        files = await widget_service.generate_widget_files(tenant_id, access_token=None)

        # Choose minified or full version
        js_content = files["chat-widget.min.js"] if minified else files["chat-widget.js"]

        return Response(
            content=js_content,
            media_type="application/javascript",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Content-Type": "application/javascript; charset=utf-8",
                "X-Content-Type-Options": "nosniff"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to serve widget JavaScript: {str(e)}"
        )


@router.get("/widget/static/{filename}")
async def get_widget_static_asset(filename: str):
    """Serve static assets for the chat widget (logos, icons, etc.)"""

    # Security: Only allow specific whitelisted files
    allowed_files = [
        "chatcraft-logo2.png",
        "factorialbot_logo.svg",
        "favicon.ico"
    ]

    if filename not in allowed_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    # Construct the file path
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    file_path = os.path.join(static_dir, filename)

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    # Determine media type based on file extension
    media_types = {
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }

    file_ext = os.path.splitext(filename)[1].lower()
    media_type = media_types.get(file_ext, "application/octet-stream")

    return FileResponse(
        file_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "Content-Disposition": f"inline; filename={filename}"
        }
    )