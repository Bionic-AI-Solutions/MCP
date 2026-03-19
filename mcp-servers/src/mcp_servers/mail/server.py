"""
Mail MCP Server (Multi-tenant)

A FastMCP server providing email sending operations with multi-tenant support.
"""

import json
import base64
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, EmailStr
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from mcp_servers.mail.tenant_manager import MailTenantManager, MailTenantConfig
except ImportError:
    from .tenant_manager import MailTenantManager, MailTenantConfig

# Initialize tenant manager
tenant_manager = MailTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all HTTP clients and Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("Mail Server", lifespan=lifespan)


# ============================================================================
# Request/Response Models
# ============================================================================

class SendEmailRequest(BaseModel):
    """Request model for sending emails."""

    to: List[EmailStr] = Field(..., description="List of recipient email addresses")
    cc: Optional[List[EmailStr]] = Field(
        default=None, description="List of CC email addresses"
    )
    bcc: Optional[List[EmailStr]] = Field(
        default=None, description="List of BCC email addresses"
    )
    subject: str = Field(..., min_length=1, max_length=200, description="Email subject")
    body: str = Field(..., min_length=1, description="Email body content")
    body_type: str = Field(
        default="text", description="Body type: 'text' or 'html'"
    )
    from_email: Optional[EmailStr] = Field(
        default=None, description="Sender email address"
    )
    from_name: Optional[str] = Field(default=None, description="Sender name")
    reply_to: Optional[EmailStr] = Field(
        default=None, description="Reply-to email address"
    )


class AttachmentInput(BaseModel):
    """Attachment input model for MCP tool."""

    filename: str = Field(..., description="Name of the attachment file")
    content: str = Field(
        ..., description="File content as base64-encoded string"
    )
    content_type: str = Field(
        default="application/octet-stream", description="MIME type of the file"
    )


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def mail_send_email(
    tenant_id: str,
    to: List[EmailStr],
    subject: str,
    body: str,
    cc: Optional[List[EmailStr]] = None,
    bcc: Optional[List[EmailStr]] = None,
    body_type: str = "text",
    from_email: Optional[EmailStr] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[EmailStr] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Send a single email via the mail service API.

    Composes and delivers one email message to one or more recipients through
    the tenant's configured mail service. Use this tool when you need to send a
    plain-text or HTML email without any file attachments. If you need to attach
    files, use mail_send_email_with_attachments instead. If you need to send
    many distinct emails at once, use mail_send_bulk_emails for better
    throughput.

    The sender address (from_email / from_name) falls back to the tenant's
    configured defaults when not explicitly provided.

    Args:
        tenant_id: (str) Tenant identifier whose mail service configuration
            should be used to send the email. The tenant must already be
            registered via mail_register_tenant.
        to: (List[EmailStr]) List of recipient email addresses. At least one
            address is required. Each entry must be a valid RFC 5322 email
            address (e.g., "user@example.com").
        subject: (str) The email subject line. Must be between 1 and 200
            characters.
        body: (str) The email body content. Interpreted as plain text by default;
            set body_type to "html" to send rich HTML content. When using HTML,
            include inline CSS for best cross-client rendering.
        cc: (Optional[List[EmailStr]], default=None) List of CC (carbon copy)
            recipient email addresses. These recipients are visible to all
            other recipients.
        bcc: (Optional[List[EmailStr]], default=None) List of BCC (blind carbon
            copy) recipient email addresses. These recipients are hidden from
            all other recipients.
        body_type: (str, default="text") The content type of the email body.
            Accepted values are "text" for plain-text emails or "html" for
            HTML-formatted emails.
        from_email: (Optional[EmailStr], default=None) The sender email address
            shown in the "From" header. If not provided, the tenant's
            default_from_email is used.
        from_name: (Optional[str], default=None) The sender display name shown
            alongside the sender email address. If not provided, the tenant's
            default_from_name is used.
        reply_to: (Optional[EmailStr], default=None) An email address to use as
            the Reply-To header. When set, replies from recipients will be
            directed to this address instead of the from_email address.

    Returns:
        Dict with:
        - success (bool): Whether the email was sent successfully.
        - message_id (str | None): The unique identifier assigned to the sent
          message by the mail service, or None on failure.
        - recipients_count (int): The number of recipients the email was
          delivered to (includes to, cc, and bcc).
        - error (str | None): Error message if the operation failed, or None
          on success.

    Note:
        The subject line should be kept concise (under 200 characters). For HTML
        body content, keep in mind that some email clients strip external CSS
        and JavaScript, so use inline styles for reliable rendering.
    """
    if ctx:
        await ctx.info(f"Sending email for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        config = tenant_manager.configs[tenant_id]

        # Build request payload
        payload = {
            "to": to,
            "subject": subject,
            "body": body,
            "body_type": body_type,
        }

        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        if from_email:
            payload["from_email"] = from_email
        elif config.default_from_email:
            payload["from_email"] = config.default_from_email
        if from_name:
            payload["from_name"] = from_name
        elif config.default_from_name:
            payload["from_name"] = config.default_from_name
        if reply_to:
            payload["reply_to"] = reply_to

        # Call mail API
        response = await client.post("/send-email", json=payload)
        response.raise_for_status()
        result = response.json()

        return {
            "success": result.get("success", True),
            "message_id": result.get("message_id"),
            "recipients_count": result.get("recipients_count", 0),
            "error": result.get("error"),
        }
    except Exception as e:
        error_msg = str(e)
        if ctx:
            await ctx.error(f"Failed to send email: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "message_id": None,
            "recipients_count": 0,
        }


@mcp.tool
async def mail_send_email_with_attachments(
    tenant_id: str,
    to: List[EmailStr],
    subject: str,
    body: str,
    attachments: List[AttachmentInput],
    cc: Optional[List[EmailStr]] = None,
    bcc: Optional[List[EmailStr]] = None,
    body_type: str = "text",
    from_email: Optional[EmailStr] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[EmailStr] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Send an email with one or more file attachments via the mail service API.

    Composes and delivers an email message that includes file attachments. The
    request is sent as multipart form data so that binary file content can be
    transmitted alongside the email metadata. Use this tool when you need to
    attach documents, images, or other files to an email. For emails without
    attachments, prefer mail_send_email as it is simpler and more efficient.

    Each attachment must be provided as a base64-encoded string along with its
    filename and MIME content type. Attachments that fail to decode are skipped
    with a warning rather than aborting the entire send operation.

    The sender address (from_email / from_name) falls back to the tenant's
    configured defaults when not explicitly provided.

    Args:
        tenant_id: (str) Tenant identifier whose mail service configuration
            should be used to send the email. The tenant must already be
            registered via mail_register_tenant.
        to: (List[EmailStr]) List of recipient email addresses. At least one
            address is required. Each entry must be a valid RFC 5322 email
            address (e.g., "user@example.com").
        subject: (str) The email subject line. Must be between 1 and 200
            characters.
        body: (str) The email body content. Interpreted as plain text by default;
            set body_type to "html" to send rich HTML content.
        attachments: (List[AttachmentInput]) List of file attachments to include
            with the email. Each attachment is an object with the following
            fields:
            - filename (str): The display name of the attached file
              (e.g., "report.pdf").
            - content (str): The file content encoded as a base64 string.
            - content_type (str, default="application/octet-stream"): The MIME
              type of the file (e.g., "application/pdf", "image/png").
        cc: (Optional[List[EmailStr]], default=None) List of CC (carbon copy)
            recipient email addresses. These recipients are visible to all
            other recipients.
        bcc: (Optional[List[EmailStr]], default=None) List of BCC (blind carbon
            copy) recipient email addresses. These recipients are hidden from
            all other recipients.
        body_type: (str, default="text") The content type of the email body.
            Accepted values are "text" for plain-text emails or "html" for
            HTML-formatted emails.
        from_email: (Optional[EmailStr], default=None) The sender email address
            shown in the "From" header. If not provided, the tenant's
            default_from_email is used.
        from_name: (Optional[str], default=None) The sender display name shown
            alongside the sender email address. If not provided, the tenant's
            default_from_name is used.
        reply_to: (Optional[EmailStr], default=None) An email address to use as
            the Reply-To header. When set, replies from recipients will be
            directed to this address instead of the from_email address.

    Returns:
        Dict with:
        - success (bool): Whether the email was sent successfully.
        - message_id (str | None): The unique identifier assigned to the sent
          message by the mail service, or None on failure.
        - recipients_count (int): The number of recipients the email was
          delivered to (includes to, cc, and bcc).
        - error (str | None): Error message if the operation failed, or None
          on success.

    Note:
        Attachment content must be base64-encoded. If any individual attachment
        fails to decode from base64, it will be silently skipped (a warning is
        logged) and the email will still be sent with the remaining valid
        attachments. Be mindful of total attachment size limits imposed by the
        underlying mail service, which commonly cap at 10-25 MB total.
    """
    if ctx:
        await ctx.info(f"Sending email with attachments for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        config = tenant_manager.configs[tenant_id]

        # Prepare multipart form data
        # FastAPI expects lists as multiple form fields with the same name
        # For httpx, we need to combine data and files into a single files parameter
        files_data = []

        # Add 'to' recipients (multiple fields with same name)
        for recipient in to:
            files_data.append(("to", (None, recipient)))

        files_data.append(("subject", (None, subject)))
        files_data.append(("body", (None, body)))
        files_data.append(("body_type", (None, body_type)))

        if cc:
            for recipient in cc:
                files_data.append(("cc", (None, recipient)))
        if bcc:
            for recipient in bcc:
                files_data.append(("bcc", (None, recipient)))
        if from_email:
            files_data.append(("from_email", (None, from_email)))
        elif config.default_from_email:
            files_data.append(("from_email", (None, config.default_from_email)))
        if from_name:
            files_data.append(("from_name", (None, from_name)))
        elif config.default_from_name:
            files_data.append(("from_name", (None, config.default_from_name)))
        if reply_to:
            files_data.append(("reply_to", (None, reply_to)))

        # Add file attachments
        for attachment in attachments:
            try:
                content_bytes = base64.b64decode(attachment.content)
                files_data.append(
                    (
                        "attachments",
                        (
                            attachment.filename,
                            content_bytes,
                            attachment.content_type,
                        ),
                    )
                )
            except Exception as e:
                if ctx:
                    await ctx.warning(
                        f"Failed to decode attachment {attachment.filename}: {e}"
                    )
                continue

        # Call mail API with multipart form data
        # httpx handles multipart automatically when files are provided
        response = await client.post(
            "/send-email-with-attachments", files=files_data
        )
        response.raise_for_status()
        result = response.json()

        return {
            "success": result.get("success", True),
            "message_id": result.get("message_id"),
            "recipients_count": result.get("recipients_count", 0),
            "error": result.get("error"),
        }
    except Exception as e:
        error_msg = str(e)
        if ctx:
            await ctx.error(f"Failed to send email with attachments: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "message_id": None,
            "recipients_count": 0,
        }


@mcp.tool
async def mail_send_bulk_emails(
    tenant_id: str,
    emails: List[Dict[str, Any]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Send multiple emails concurrently in a single batch via the mail service API.

    Accepts a list of email specifications and sends them all in one API call
    to the mail service, which processes them concurrently for maximum
    throughput. Use this tool when you need to send many distinct emails (e.g.,
    notifications, newsletters, or personalized messages to different
    recipients) rather than calling mail_send_email repeatedly in a loop.

    Each email in the batch can have its own recipients, subject, body, and
    other parameters. The sender address falls back to the tenant's configured
    defaults when not explicitly provided in an individual email entry.

    This tool does not support attachments. If any emails require attachments,
    send those separately using mail_send_email_with_attachments.

    Args:
        tenant_id: (str) Tenant identifier whose mail service configuration
            should be used to send the emails. The tenant must already be
            registered via mail_register_tenant.
        emails: (List[Dict[str, Any]]) A list of email specification objects.
            Each object in the list is a dictionary with the following keys:
            - to (List[str], required): List of recipient email addresses.
            - subject (str, required): The email subject line.
            - body (str, required): The email body content.
            - body_type (str, optional, default="text"): "text" or "html".
            - cc (List[str], optional): List of CC email addresses.
            - bcc (List[str], optional): List of BCC email addresses.
            - from_email (str, optional): Sender email address override.
            - from_name (str, optional): Sender display name override.
            - reply_to (str, optional): Reply-to email address.

    Returns:
        Dict with:
        - success (bool): Whether the bulk operation completed (True even if
          some individual emails failed; False only if the entire API call
          failed).
        - total_emails (int): Total number of emails in the batch.
        - successful (int): Number of emails that were sent successfully.
        - failed (int): Number of emails that failed to send.
        - results (List[Dict]): Per-email result list, where each entry
          contains the success status, message_id, and any error for that
          individual email.
        - error (str): Present only when the entire bulk operation failed;
          contains the error message.

    Note:
        The mail service may impose rate limits on bulk sending. If the batch
        is very large, consider splitting it into smaller batches. Individual
        email failures within a batch do not cause the entire operation to
        fail -- check the "results" list to identify which emails succeeded
        and which did not.
    """
    if ctx:
        await ctx.info(f"Sending {len(emails)} emails for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        config = tenant_manager.configs[tenant_id]

        # Prepare email requests
        requests = []
        for email in emails:
            request = {
                "to": email.get("to", []),
                "subject": email.get("subject", ""),
                "body": email.get("body", ""),
                "body_type": email.get("body_type", "text"),
            }

            if "cc" in email:
                request["cc"] = email["cc"]
            if "bcc" in email:
                request["bcc"] = email["bcc"]
            if "from_email" in email:
                request["from_email"] = email["from_email"]
            elif config.default_from_email:
                request["from_email"] = config.default_from_email
            if "from_name" in email:
                request["from_name"] = email["from_name"]
            elif config.default_from_name:
                request["from_name"] = config.default_from_name
            if "reply_to" in email:
                request["reply_to"] = email["reply_to"]

            requests.append(request)

        # Call mail API
        response = await client.post("/send-bulk-emails", json=requests)
        response.raise_for_status()
        results = response.json()

        # Aggregate results
        success_count = sum(1 for r in results if r.get("success", False))
        total_count = len(results)

        return {
            "success": True,
            "total_emails": total_count,
            "successful": success_count,
            "failed": total_count - success_count,
            "results": results,
        }
    except Exception as e:
        error_msg = str(e)
        if ctx:
            await ctx.error(f"Failed to send bulk emails: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "total_emails": len(emails),
            "successful": 0,
            "failed": len(emails),
            "results": [],
        }


@mcp.tool
async def mail_register_tenant(
    tenant_id: str,
    api_key: str,
    mail_api_url: Optional[str] = None,
    default_from_email: Optional[EmailStr] = None,
    default_from_name: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant configuration for the mail service.

    Creates or updates a tenant entry that holds the credentials and defaults
    needed to send emails through the mail service API. This must be called
    before any of the email-sending tools (mail_send_email,
    mail_send_email_with_attachments, mail_send_bulk_emails) can be used for
    the given tenant. If a tenant with the same tenant_id already exists, its
    configuration will be overwritten.

    The registered configuration is persisted so that it survives server
    restarts. Default sender information (from_email and from_name) set here
    will be used automatically by the sending tools whenever the caller does
    not explicitly provide sender details.

    Args:
        tenant_id: (str) A unique identifier for the tenant. This value is
            used in all subsequent email-sending calls to select the correct
            mail service configuration. Choose a stable, descriptive ID
            (e.g., "acme-corp", "project-alpha").
        api_key: (str) The API key used to authenticate with the tenant's mail
            service. This is sent as a credential in requests to the mail API
            and must have sufficient permissions to send emails.
        mail_api_url: (Optional[str], default="http://mail-service.mail") The
            base URL of the mail service API for this tenant. Override this
            when the tenant uses a custom or non-default mail service endpoint.
        default_from_email: (Optional[EmailStr], default=None) The default
            sender email address to use when from_email is not provided in
            individual send calls. Must be a valid email address that the mail
            service is authorized to send from.
        default_from_name: (Optional[str], default=None) The default sender
            display name to use when from_name is not provided in individual
            send calls (e.g., "Acme Support Team").

    Returns:
        Dict with:
        - success (bool): Whether the tenant was registered successfully.
        - message (str): A confirmation message on success
          (e.g., "Tenant 'acme-corp' registered successfully").
        - error (str): Error message if the registration failed (only present
          on failure).

    Note:
        The api_key is stored securely and is never exposed through resource
        endpoints or info queries. If you need to rotate an API key, simply
        call this tool again with the same tenant_id and the new api_key to
        update the configuration in place.
    """
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    try:
        config = MailTenantConfig(
            tenant_id=tenant_id,
            api_key=api_key,
            mail_api_url=mail_api_url or "http://mail-service.mail",
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )

        await tenant_manager.register_tenant(config)
        return {
            "success": True,
            "message": f"Tenant '{tenant_id}' registered successfully",
        }
    except Exception as e:
        error_msg = str(e)
        if ctx:
            await ctx.error(f"Failed to register tenant: {error_msg}")
        return {"success": False, "error": error_msg}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("mail://{tenant_id}/info")
async def get_tenant_info(tenant_id: str) -> str:
    """Get information about a tenant configuration."""
    try:
        config = tenant_manager.configs.get(tenant_id)
        if config:
            # Don't expose the API key in the resource
            info = {
                "tenant_id": config.tenant_id,
                "mail_api_url": config.mail_api_url,
                "default_from_email": config.default_from_email,
                "default_from_name": config.default_from_name,
            }
            return json.dumps(info, indent=2)
        else:
            return json.dumps({"error": f"Tenant '{tenant_id}' not found"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("mail://info")
def mail_info() -> str:
    """Get information about the Mail MCP server."""
    return "Mail MCP Server - Multi-tenant email sending operations"


# ============================================================================
# Custom Routes
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for monitoring."""
    return JSONResponse({
        "status": "healthy",
        "service": "mail-mcp-server",
        "version": "1.0.0"
    })


def main():
    """Run the Mail server with HTTP transport for remote access."""
    import os

    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8005"))
    # Enable stateless HTTP mode for better compatibility with MCP clients like Cursor
    # This allows each request to work independently without session management
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    # Enable JSON response format for better Cursor compatibility
    # JSON format returns plain JSON instead of SSE format
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    # HTTP transport provides native MCP protocol support at /mcp endpoint
    # FastMCP automatically handles streamable HTTP protocol
    mcp.run(
        transport=transport,
        host=host,
        port=port,
        stateless_http=stateless,
        json_response=json_response,
    )


if __name__ == "__main__":
    main()
