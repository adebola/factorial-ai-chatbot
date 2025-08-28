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
from ..services.dependencies import get_current_tenant
from ..models.tenant import Tenant

router = APIRouter()


@router.get("/tenants/{tenant_id}/widget/generate", response_model=Dict[str, Any])
async def generate_widget_files(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Generate or regenerate widget files for a tenant"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only generate widgets for your own organization."
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
        return {
            "message": "Widget files generated successfully",
            "tenant_id": tenant_id,
            "tenant_name": current_tenant.name,
            "files_generated": list(files.keys()),
            "generated_at": datetime.utcnow().isoformat(),
            "download_urls": {
                "javascript": f"/api/v1/tenants/{tenant_id}/widget/chat-widget.js",
                "css": f"/api/v1/tenants/{tenant_id}/widget/chat-widget.css", 
                "demo_html": f"/api/v1/tenants/{tenant_id}/widget/chat-widget.html",
                "integration_guide": f"/api/v1/tenants/{tenant_id}/widget/integration-guide.html",
                "download_all": f"/api/v1/tenants/{tenant_id}/widget/download-all"
            },
            "integration_snippet": f'<script src="https://your-domain.com/path/to/chat-widget.js"></script>',
            "widget_features": [
                "Real-time AI chat",
                "Mobile responsive design",
                "Custom branding with your colors",
                "Secure WebSocket connection",
                "Dark mode support",
                "Lightweight and fast loading"
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate widget files: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/widget/chat-widget.js")
async def download_widget_javascript(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """Download the chat widget JavaScript file"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
        return Response(
            content=files["chat-widget.js"],
            media_type="application/javascript",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-{tenant_id[:8]}.js",
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


@router.get("/tenants/{tenant_id}/widget/chat-widget.css")
async def download_widget_css(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """Download the chat widget CSS file"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
        return Response(
            content=files["chat-widget.css"],
            media_type="text/css",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-{tenant_id[:8]}.css",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate CSS file: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/widget/chat-widget.html")
async def download_widget_demo(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """Download the chat widget demo HTML file"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
        return Response(
            content=files["chat-widget.html"],
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=chat-widget-demo-{tenant_id[:8]}.html"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate demo HTML file: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/widget/integration-guide.html")
async def download_integration_guide(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """Download the integration guide HTML file"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
        return Response(
            content=files["integration-guide.html"],
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=integration-guide-{tenant_id[:8]}.html"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate integration guide: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/widget/download-all")
async def download_all_widget_files(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """Download all widget files as a ZIP archive"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
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
                readme_content = f"""FactorialBot Chat Widget - {current_tenant.name}
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
            
            zip_filename = f"factorial-chat-widget-{current_tenant.name.lower().replace(' ', '-')}-{tenant_id[:8]}.zip"
            
            return FileResponse(
                temp_zip.name,
                media_type="application/zip",
                filename=zip_filename,
                headers={
                    "Content-Disposition": f"attachment; filename={zip_filename}"
                }
            )
            
    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_zip' in locals():
            try:
                os.unlink(temp_zip.name)
            except:
                pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create widget package: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/widget/preview")
async def preview_widget(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """Preview the chat widget in a demo page"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        widget_service = WidgetService(db)
        files = widget_service.generate_widget_files(current_tenant)
        
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


@router.get("/tenants/{tenant_id}/widget/status")
async def get_widget_status(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get widget configuration status and information"""
    
    # Verify tenant access
    if current_tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return {
        "widget_status": "active",
        "tenant_id": tenant_id,
        "tenant_name": current_tenant.name,
        "api_key_configured": bool(current_tenant.api_key),
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
            "javascript": f"/api/v1/tenants/{tenant_id}/widget/chat-widget.js",
            "css": f"/api/v1/tenants/{tenant_id}/widget/chat-widget.css",
            "demo": f"/api/v1/tenants/{tenant_id}/widget/chat-widget.html",
            "guide": f"/api/v1/tenants/{tenant_id}/widget/integration-guide.html",
            "all_files": f"/api/v1/tenants/{tenant_id}/widget/download-all",
            "preview": f"/api/v1/tenants/{tenant_id}/widget/preview"
        }
    }