import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional, Any, Dict

# Environment variables for authentication
EDA_URL = os.getenv("EDA_URL")
EDA_TOKEN = os.getenv("EDA_TOKEN")

if not EDA_TOKEN:
    raise ValueError("EDA_TOKEN environment variable is required")

# Headers for API authentication
HEADERS = {
    "Authorization": f"Bearer {EDA_TOKEN}",
    "Content-Type": "application/json"
}

# Initialize FastMCP
mcp = FastMCP("eda")

async def make_request(url: str, *, method: str = "GET", params: Optional[Dict] = None, json: Optional[Dict] = None) -> Any:
    """Helper function to make authenticated API requests to EDA."""
    async with httpx.AsyncClient() as client:
        #logging.info(f"make_request.url = {url}")
        #logging.info(f"make_request.method = {method}")
        #logging.info(f"make_request.params = {params}")
        #logging.info(f"make_request.json = {json}")
        response = await client.request(method, url, headers=HEADERS, params=params, json=json)
    if response.status_code not in [200, 201, 204]:
        return f"Error {response.status_code}: {response.text}"
    return response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text

@mcp.tool()
async def list_activations() -> Any:
    """List all activations in Event-Driven Ansible."""
    return await make_request(f"{EDA_URL}/activations/")

@mcp.tool()
async def get_activation(activation_id: int) -> Any:
    """Get details of a specific activation."""
    return await make_request(f"{EDA_URL}/activations/{activation_id}/")

@mcp.tool()
async def create_activation(payload: Dict) -> Any:
    """Create a new activation."""
    return await make_request(f"{EDA_URL}/activations/", method="POST", json=payload)

@mcp.tool()
async def disable_activation(activation_id: int) -> Any:
    """Disable an activation."""
    return await make_request(f"{EDA_URL}/activations/{activation_id}/disable/", method="POST")

@mcp.tool()
async def enable_activation(activation_id: int) -> Any:
    """Enable an activation."""
    return await make_request(f"{EDA_URL}/activations/{activation_id}/enable/", method="POST")

@mcp.tool()
async def restart_activation(activation_id: int) -> Any:
    """Restart an activation."""
    return await make_request(f"{EDA_URL}/activations/{activation_id}/restart/", method="POST")

@mcp.tool()
async def delete_activation(activation_id: int) -> Any:
    """Delete an activation."""
    return await make_request(f"{EDA_URL}/activations/{activation_id}/", method="DELETE")

@mcp.tool()
async def list_decision_environments() -> Any:
    """List all decision environments."""
    return await make_request(f"{EDA_URL}/decision-environments/")

@mcp.tool()
async def create_decision_environment(payload: Dict) -> Any:
    """Create a new decision environment."""
    return await make_request(f"{EDA_URL}/decision-environments/", method="POST", json=payload)

@mcp.tool()
async def list_rulebooks() -> Any:
    """List all rulebooks in EDA."""
    return await make_request(f"{EDA_URL}/rulebooks/")

@mcp.tool()
async def get_rulebook(rulebook_id: int) -> Any:
    """Retrieve details of a specific rulebook."""
    return await make_request(f"{EDA_URL}/rulebooks/{rulebook_id}/")

@mcp.tool()
async def list_event_streams() -> Any:
    """List all event streams."""
    return await make_request(f"{EDA_URL}/event-streams/")

@mcp.tool()
async def list_rule_audits() -> Any:
    """List all rule audits"""
    return await make_request(f"{EDA_URL}/audit-rules/")

@mcp.tool()
async def get_rule_audit(rulebook_id: int) -> Any:
    """Get the audit of a specific rule"""
    return await make_request(f"{EDA_URL}/audit-rules/{rulebook_id}")

@mcp.tool()
async def get_rule_activation_audit(activation_id: int) -> Any:
    """Get the audit of a specific rule activation"""
    params = {"activation_instance_id": str(activation_id)}
    return await make_request(f"{EDA_URL}/audit-rules/", params=params)


if __name__ == "__main__":
    mcp.run(transport="stdio")

