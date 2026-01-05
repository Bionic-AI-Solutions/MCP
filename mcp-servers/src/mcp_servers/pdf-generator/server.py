"""
PDF Generator MCP Server (Multi-tenant)

A FastMCP server providing PDF report generation with multi-tenant support.
"""

import json
import base64
import os
import tempfile
import uuid
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.requests import Request

# Handle import for directory with hyphen in name
try:
    # Try absolute import first (works when running as module with proper package structure)
    from mcp_servers.pdf_generator.tenant_manager import PdfGeneratorTenantManager
except ImportError:
    # Use importlib to handle directory with hyphen
    import importlib.util
    tenant_manager_path = os.path.join(os.path.dirname(__file__), "tenant_manager.py")
    spec = importlib.util.spec_from_file_location("pdf_generator_tenant_manager", tenant_manager_path)
    tenant_manager_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tenant_manager_module)
    PdfGeneratorTenantManager = tenant_manager_module.PdfGeneratorTenantManager

# Initialize tenant manager
tenant_manager = PdfGeneratorTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all connections and Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("PDF Generator Server", lifespan=lifespan)

# Temporary file storage directory
TEMP_DIR = Path(os.getenv("PDF_TEMP_DIR", "/tmp/pdf-reports"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)
FILE_RETENTION_HOURS = int(os.getenv("PDF_RETENTION_HOURS", "24"))


# ============================================================================
# Request/Response Models
# ============================================================================

class GeneratePdfRequest(BaseModel):
    """Request model for PDF generation."""

    tenant_id: str = Field(..., description="Tenant identifier")
    template: str = Field(..., description="HTML template or template name")
    content: Dict[str, Any] = Field(..., description="Content data to fill the template")
    filename: Optional[str] = Field(default=None, description="Optional filename for the PDF")
    return_format: str = Field(
        default="base64",
        description="Return format: 'base64' for data stream, 'url' for temporary file URL"
    )


# ============================================================================
# PDF Generation Utilities
# ============================================================================

def render_template(template: str, content: Dict[str, Any]) -> str:
    """Render HTML template with content data."""
    html = template
    # Simple template variable replacement: {{variable_name}}
    for key, value in content.items():
        placeholder = f"{{{{{key}}}}}"
        html = html.replace(placeholder, str(value))
    return html


def generate_pdf_from_html(html_content: str, output_path: str) -> None:
    """Generate PDF from HTML content using weasyprint."""
    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
    except ImportError:
        # Fallback to reportlab if weasyprint not available
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from html import unescape
        import re
        
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Simple HTML to reportlab conversion
        # Remove HTML tags and extract text
        text = re.sub(r'<[^>]+>', '', html_content)
        text = unescape(text)
        
        for line in text.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), styles['Normal']))
                story.append(Spacer(1, 12))
        
        doc.build(story)


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def pdf_generate_pdf(
    tenant_id: str,
    template: str,
    content: Dict[str, Any],
    filename: Optional[str] = None,
    return_format: str = "base64",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate a PDF report from a template and content.
    
    Args:
        tenant_id: Tenant identifier
        template: HTML template string with {{variable}} placeholders or template name
        content: Dictionary of data to fill into the template
        filename: Optional filename for the PDF (default: auto-generated)
        return_format: 'base64' to return PDF as base64 data stream, 'url' for temporary file URL
        
    Returns:
        Dictionary with PDF data or URL
    """
    if ctx:
        await ctx.info(f"Generating PDF for tenant: {tenant_id}")
    
    try:
        # Get tenant config (for future use - e.g., custom templates per tenant)
        config = tenant_manager.configs.get(tenant_id)
        
        # Render template with content
        html_content = render_template(template, content)
        
        # Generate filename if not provided
        if not filename:
            filename = f"report_{tenant_id}_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Ensure filename ends with .pdf
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        
        # Create temporary file
        pdf_path = TEMP_DIR / filename
        generate_pdf_from_html(html_content, str(pdf_path))
        
        if return_format == "url":
            # Return temporary file URL
            # In production, you might want to serve this via a web server
            file_id = uuid.uuid4().hex
            file_url = f"https://mcp.bionicaisolutions.com/pdf-generator/file/{file_id}"
            
            # Store file mapping (in production, use Redis or database)
            # For now, we'll use a simple approach with the filename
            # In a real implementation, you'd store file_id -> filename mapping
            
            return {
                "success": True,
                "file_id": file_id,
                "url": file_url,
                "filename": filename,
                "expires_at": (datetime.now() + timedelta(hours=FILE_RETENTION_HOURS)).isoformat(),
                "message": f"PDF generated successfully. Access via URL: {file_url}"
            }
        else:
            # Return base64 encoded PDF
            with open(pdf_path, 'rb') as f:
                pdf_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Clean up file if returning as base64
            pdf_path.unlink()
            
            return {
                "success": True,
                "filename": filename,
                "data": pdf_data,
                "format": "base64",
                "size_bytes": len(pdf_data),
                "message": "PDF generated successfully as base64 data stream"
            }
            
    except Exception as e:
        error_msg = f"Error generating PDF: {str(e)}"
        if ctx:
            await ctx.error(error_msg)
        return {
            "success": False,
            "error": error_msg
        }


@mcp.tool
async def pdf_get_pdf_file(
    file_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Retrieve a previously generated PDF file by ID.
    
    Args:
        file_id: File ID returned from generate_pdf when using 'url' format
        
    Returns:
        Dictionary with PDF data or error
    """
    if ctx:
        await ctx.info(f"Retrieving PDF file: {file_id}")
    
    # In production, look up file_id -> filename mapping from Redis/database
    # For now, this is a placeholder
    return {
        "success": False,
        "error": "File retrieval not yet implemented. Use return_format='base64' for direct PDF data."
    }


@mcp.tool
async def pdf_register_tenant(
    tenant_id: str,
    storage_path: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant configuration.
    
    Args:
        tenant_id: Unique tenant identifier
        storage_path: Optional custom storage path for this tenant's PDFs
    """
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    # Handle import for directory with hyphen in name
    try:
        from mcp_servers.pdf_generator.tenant_manager import PdfGeneratorTenantConfig
    except ImportError:
        import importlib.util
        tenant_manager_path = os.path.join(os.path.dirname(__file__), "tenant_manager.py")
        spec = importlib.util.spec_from_file_location("pdf_generator_tenant_manager", tenant_manager_path)
        tenant_manager_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tenant_manager_module)
        PdfGeneratorTenantConfig = tenant_manager_module.PdfGeneratorTenantConfig

    config = PdfGeneratorTenantConfig(
        tenant_id=tenant_id,
        storage_path=storage_path,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("pdf-generator://{tenant_id}/info")
async def get_info_resource(tenant_id: str) -> str:
    """Get information about a tenant as a resource."""
    config = tenant_manager.configs.get(tenant_id)
    result = {
        "tenant_id": tenant_id,
        "status": "active" if config else "not_registered",
        "storage_path": config.storage_path if config else None,
    }
    return json.dumps(result, indent=2)


@mcp.resource("pdf-generator://info")
def server_info() -> str:
    """Get information about the PDF Generator MCP server."""
    return json.dumps({
        "name": "PDF Generator MCP Server",
        "description": "Multi-tenant PDF report generation",
        "features": [
            "HTML template rendering",
            "Base64 PDF data stream",
            "Temporary file URLs",
            "Multi-tenant support"
        ],
        "temp_directory": str(TEMP_DIR),
        "file_retention_hours": FILE_RETENTION_HOURS
    }, indent=2)


# ============================================================================
# Health Check Endpoint
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for monitoring and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "service": "pdf-generator-mcp-server",
        "version": "1.0.0"
    })


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the PDF Generator server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8003"))
    # Enable stateless HTTP mode for better compatibility with MCP clients like Cursor
    # This allows each request to work independently without session management
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    # Enable JSON response format for better Cursor compatibility
    # JSON format returns plain JSON instead of SSE format
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    # HTTP transport provides native MCP protocol support at /mcp endpoint
    # FastMCP automatically handles streamable HTTP protocol
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()

