"""
Mail MCP Client

Example client for interacting with the Mail MCP server.
"""

import asyncio
from fastmcp import Client


async def main():
    """Example usage of the Mail MCP client."""
    # Connect to the mail server
    async with Client("src/mcp_servers/mail/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}")

        # Register a tenant (if not already configured via env vars)
        tenant_id = "1"
        print(f"\n=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "mail_register_tenant",
            {
                "tenant_id": tenant_id,
                "api_key": "your-jwt-token-here",
                "mail_api_url": "http://mail-service.mail:8000",
            },
        )
        print(f"Result: {result.content[0].text}")

        # Send an email
        print(f"\n=== Sending email for tenant: {tenant_id} ===")
        result = await client.call_tool(
            "mail_send_email",
            {
                "tenant_id": tenant_id,
                "to": ["recipient@example.com"],
                "subject": "Test Email",
                "body": "This is a test email from the Mail MCP server.",
                "body_type": "text",
            },
        )
        print(f"Result: {result.content[0].text}")

        # Send bulk emails
        print(f"\n=== Sending bulk emails ===")
        result = await client.call_tool(
            "mail_send_bulk_emails",
            {
                "tenant_id": tenant_id,
                "emails": [
                    {
                        "to": ["user1@example.com"],
                        "subject": "Bulk Email 1",
                        "body": "First email in bulk send",
                    },
                    {
                        "to": ["user2@example.com"],
                        "subject": "Bulk Email 2",
                        "body": "Second email in bulk send",
                    },
                ],
            },
        )
        print(f"Result: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())


