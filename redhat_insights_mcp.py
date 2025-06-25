"""
Red Hat Insights MCP Server

This server requires a Red Hat service account with client credentials.

Setup:
1. Create a service account in Red Hat Console (console.redhat.com)
2. Assign appropriate permissions via User Access → Groups
3. Set environment variables:
   export INSIGHTS_CLIENT_ID="your-client-id"
   export INSIGHTS_CLIENT_SECRET="your-client-secret"
   
Optional:
   export INSIGHTS_BASE_URL="https://console.redhat.com/api"
   export SSO_URL="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
"""

import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Any, Optional
from datetime import datetime, timedelta

# Environment variables for authentication
INSIGHTS_BASE_URL = os.getenv("INSIGHTS_BASE_URL", "https://console.redhat.com/api")
INSIGHTS_CLIENT_ID = os.getenv("INSIGHTS_CLIENT_ID")
INSIGHTS_CLIENT_SECRET = os.getenv("INSIGHTS_CLIENT_SECRET")
SSO_URL = os.getenv("SSO_URL", "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token")

if not INSIGHTS_CLIENT_ID or not INSIGHTS_CLIENT_SECRET:
    raise ValueError("INSIGHTS_CLIENT_ID and INSIGHTS_CLIENT_SECRET are required")

# Global variable to store the access token
_access_token = None
_token_expires_at = None

# Initialize FastMCP
mcp = FastMCP("insights")

async def get_access_token() -> str:
    """Get or refresh the access token using client credentials."""
    global _access_token, _token_expires_at
    
    # Check if we have a valid token
    if _access_token and _token_expires_at and datetime.utcnow() < _token_expires_at:
        return _access_token
    
    # Request new token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SSO_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "scope": "api.console",
                "client_id": INSIGHTS_CLIENT_ID,
                "client_secret": INSIGHTS_CLIENT_SECRET
            }
        )
    
    if response.status_code != 200:
        raise Exception(f"Failed to get access token: {response.status_code} {response.text}")
    
    token_data = response.json()
    _access_token = token_data["access_token"]
    # Set expiration time with some buffer (subtract 60 seconds)
    expires_in = token_data.get("expires_in", 300)  # Default to 5 minutes
    _token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
    
    return _access_token

async def make_request(url: str, method: str = "GET", json: dict = None, params: dict = None) -> Any:
    """Helper function to make authenticated API requests to Red Hat Insights."""
    token = await get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, json=json, params=params)
    
    if response.status_code not in [200, 201, 204]:
        return f"Error {response.status_code}: {response.text}"
    
    return response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text

# Authentication Test
@mcp.tool()
async def test_authentication() -> Any:
    """Test authentication with Red Hat Insights using service account credentials."""
    try:
        token = await get_access_token()
        # Test with a simple API call
        result = await make_request(f"{INSIGHTS_BASE_URL}/inventory/v1/hosts?limit=1")
        return {"status": "success", "message": "Authentication successful", "sample_data": result}
    except Exception as e:
        return {"status": "error", "message": f"Authentication failed: {str(e)}"}

# Host Inventory Management Tools
@mcp.tool()
async def list_systems(limit: int = 50, offset: int = 0, display_name: str = None, staleness: str = None) -> Any:
    """List all hosts/systems registered with Red Hat Insights. Use staleness='fresh' or 'stale' to filter."""
    params = {"limit": limit, "offset": offset}
    if display_name:
        params["display_name"] = display_name
    if staleness:
        params["staleness"] = staleness
    return await make_request(f"{INSIGHTS_BASE_URL}/inventory/v1/hosts", params=params)

@mcp.tool()
async def get_system(system_id: str) -> Any:
    """Get details of a specific system by UUID."""
    return await make_request(f"{INSIGHTS_BASE_URL}/inventory/v1/hosts/{system_id}")

@mcp.tool()
async def get_system_profile(system_id: str, fields: list[str] = None) -> Any:
    """Get system profile/facts for a specific system. Specify fields to limit response."""
    url = f"{INSIGHTS_BASE_URL}/inventory/v1/hosts/{system_id}/system_profile"
    params = {}
    if fields:
        for field in fields:
            params[f"fields[system_profile]"] = field
    return await make_request(url, params=params)

@mcp.tool()
async def get_system_tags(system_id: str) -> Any:
    """Get tags for a specific system."""
    return await make_request(f"{INSIGHTS_BASE_URL}/inventory/v1/hosts/{system_id}/tags")

@mcp.tool()
async def delete_system(system_id: str) -> Any:
    """Remove a system from Red Hat Insights inventory."""
    return await make_request(f"{INSIGHTS_BASE_URL}/inventory/v1/hosts/{system_id}", method="DELETE")

# Vulnerability Management Tools
@mcp.tool()
async def list_vulnerabilities(
    limit: int = 50, 
    offset: int = 0,
    affecting: bool = True,
    cvss_score_gte: float = None,
    cvss_score_lte: float = None
) -> Any:
    """List vulnerabilities affecting your systems. Set affecting=True to only show CVEs affecting systems."""
    params = {"limit": limit, "offset": offset}
    if affecting:
        params["affecting"] = "true"
    if cvss_score_gte:
        params["cvss_score_gte"] = cvss_score_gte
    if cvss_score_lte:
        params["cvss_score_lte"] = cvss_score_lte
    return await make_request(f"{INSIGHTS_BASE_URL}/vulnerability/v1/vulnerabilities/cves", params=params)

@mcp.tool()
async def get_vulnerability_executive_report() -> Any:
    """Get executive vulnerability report with CVE summaries by severity."""
    return await make_request(f"{INSIGHTS_BASE_URL}/vulnerability/v1/report/executive")

# Patch Management Tools
@mcp.tool()
async def list_advisories(
    limit: int = 50,
    offset: int = 0,
    advisory_type: str = None,
    severity: str = None
) -> Any:
    """List available advisories (patches). Export format from patch/v3."""
    params = {"limit": limit, "offset": offset}
    if advisory_type:
        params["advisory_type"] = advisory_type
    if severity:
        params["severity"] = severity
    return await make_request(f"{INSIGHTS_BASE_URL}/patch/v3/export/advisories", params=params)

# Compliance Tools
@mcp.tool()
async def list_compliance_policies(limit: int = 50, offset: int = 0) -> Any:
    """List SCAP compliance policies."""
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/compliance/v2/policies", params=params)

@mcp.tool()
async def list_compliance_systems(assigned_or_scanned: bool = True) -> Any:
    """List systems associated with SCAP policies."""
    params = {}
    if assigned_or_scanned:
        params["filter"] = "assigned_or_scanned=true"
    return await make_request(f"{INSIGHTS_BASE_URL}/compliance/v2/systems", params=params)

@mcp.tool()
async def associate_compliance_policy(policy_id: str, system_id: str) -> Any:
    """Associate a system with a SCAP compliance policy."""
    return await make_request(f"{INSIGHTS_BASE_URL}/compliance/v2/policies/{policy_id}/systems/{system_id}", method="PATCH")

@mcp.tool()
async def list_compliance_reports(limit: int = 50, offset: int = 0) -> Any:
    """List all compliance reports."""
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/compliance/v2/reports", params=params)

# Recommendations and Advisor Tools
@mcp.tool()
async def list_recommendations(
    category: str = None,
    impact: str = None,
    limit: int = 50,
    offset: int = 0
) -> Any:
    """List available recommendation rules from Advisor."""
    params = {"limit": limit, "offset": offset}
    if category:
        params["category"] = category
    if impact:
        params["impact"] = impact
    return await make_request(f"{INSIGHTS_BASE_URL}/insights/v1/rule", params=params)

@mcp.tool()
async def export_rule_hits(has_playbook: bool = None, format: str = "json") -> Any:
    """Export all rule hits (recommendations) for systems. Set has_playbook=True for Ansible playbooks."""
    params = {}
    if has_playbook:
        params["has_playbook"] = "true"
    return await make_request(f"{INSIGHTS_BASE_URL}/insights/v1/export/hits", params=params)

@mcp.tool()
async def get_system_recommendations(system_id: str) -> Any:
    """Get recommendation summary for a specific system."""
    return await make_request(f"{INSIGHTS_BASE_URL}/insights/v1/system/{system_id}")

# Policy Management Tools
@mcp.tool()
async def list_policies(limit: int = 50, offset: int = 0) -> Any:
    """List all defined custom policies."""
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/policies/v1/policies", params=params)

@mcp.tool()
async def create_policy(name: str, description: str, conditions: str, actions: str = "notification", is_enabled: bool = True) -> Any:
    """Create a new custom policy. Example conditions: 'arch = \"x86_64\"'"""
    payload = {
        "name": name,
        "description": description,
        "conditions": conditions,
        "actions": actions,
        "isEnabled": is_enabled
    }
    return await make_request(f"{INSIGHTS_BASE_URL}/policies/v1/policies", method="POST", json=payload)

@mcp.tool()
async def get_policy_triggers(policy_id: str) -> Any:
    """Get systems that triggered a specific policy."""
    return await make_request(f"{INSIGHTS_BASE_URL}/policies/v1/policies/{policy_id}/history/trigger")

# Remediation Tools
@mcp.tool()
async def list_remediations(limit: int = 50, offset: int = 0) -> Any:
    """List all defined remediation plans."""
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/remediations/v1/remediations", params=params)

@mcp.tool()
async def create_remediation(name: str, issues: list[dict], auto_reboot: bool = False, archived: bool = False) -> Any:
    """Create a new remediation plan. Issues should be list of dicts with id, resolution, systems."""
    payload = {
        "name": name,
        "auto_reboot": auto_reboot,
        "archived": archived,
        "add": {
            "issues": issues
        }
    }
    return await make_request(f"{INSIGHTS_BASE_URL}/remediations/v1/remediations", method="POST", json=payload)

@mcp.tool()
async def get_remediation_playbook(remediation_id: str) -> Any:
    """Get Ansible playbook for a remediation plan."""
    return await make_request(f"{INSIGHTS_BASE_URL}/remediations/v1/remediations/{remediation_id}/playbook")

@mcp.tool()
async def execute_remediation(remediation_id: str) -> Any:
    """Execute a remediation plan."""
    return await make_request(f"{INSIGHTS_BASE_URL}/remediations/v1/remediations/{remediation_id}/playbook_runs", method="POST")

# Subscription Management
@mcp.tool()
async def list_rhel_subscriptions(product: str = "RHEL for x86", limit: int = 50, offset: int = 0) -> Any:
    """List systems with RHEL subscriptions. Product examples: 'RHEL for x86', 'RHEL for x86_64'"""
    from urllib.parse import quote
    encoded_product = quote(product)
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/rhsm-subscriptions/v1/instances/products/{encoded_product}", params=params)

# Export Tools
@mcp.tool()
async def create_export(name: str, format: str, application: str, resource: str) -> Any:
    """Create an export request. Common applications: 'urn:redhat:application:inventory', 'subscriptions'"""
    payload = {
        "name": name,
        "format": format,
        "sources": [{
            "application": application,
            "resource": resource
        }]
    }
    return await make_request(f"{INSIGHTS_BASE_URL}/export/v1/exports", method="POST", json=payload)

@mcp.tool()
async def get_export_status(export_id: str) -> Any:
    """Get status of an export request."""
    return await make_request(f"{INSIGHTS_BASE_URL}/export/v1/exports/{export_id}/status")

@mcp.tool()
async def download_export(export_id: str) -> Any:
    """Download completed export as ZIP file."""
    return await make_request(f"{INSIGHTS_BASE_URL}/export/v1/exports/{export_id}")

# Notifications and Integrations
@mcp.tool()
async def list_notification_events(start_date: str = None, end_date: str = None, limit: int = 20, offset: int = 0) -> Any:
    """Get notification event history. Dates in YYYY-MM-DD format."""
    params = {"limit": limit, "offset": offset}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    return await make_request(f"{INSIGHTS_BASE_URL}/notifications/v1/notifications/events", params=params)

@mcp.tool()
async def list_integrations() -> Any:
    """List configured third-party integrations."""
    return await make_request(f"{INSIGHTS_BASE_URL}/integrations/v1/endpoints")

# Analytics and Statistics
@mcp.tool()
async def get_insights_overview() -> Any:
    """Get overview of systems and basic statistics by querying inventory."""
    # Use inventory endpoint to get basic stats since there's no single stats endpoint
    result = await make_request(f"{INSIGHTS_BASE_URL}/inventory/v1/hosts?limit=1")
    return result

# Content Sources and Templates
@mcp.tool()
async def list_repositories(limit: int = 50, offset: int = 0) -> Any:
    """List all existing content repositories."""
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/content-sources/v1.0/repositories", params=params)

@mcp.tool()
async def create_repository(name: str, url: str, distribution_arch: str = "x86_64", distribution_versions: list[str] = None) -> Any:
    """Create a new custom repository."""
    payload = {
        "name": name,
        "url": url,
        "distribution_arch": distribution_arch,
        "distribution_versions": distribution_versions or ["9"],
        "metadata_verification": False,
        "module_hotfixes": False,
        "snapshot": False
    }
    return await make_request(f"{INSIGHTS_BASE_URL}/content-sources/v1.0/repositories", method="POST", json=payload)

@mcp.tool()
async def list_content_templates(limit: int = 50, offset: int = 0) -> Any:
    """List all content templates."""
    params = {"limit": limit, "offset": offset}
    return await make_request(f"{INSIGHTS_BASE_URL}/content-sources/v1.0/templates", params=params)

@mcp.tool()
async def create_content_template(name: str, arch: str, version: str, repository_uuids: list[str], description: str = "") -> Any:
    """Create a new content template."""
    payload = {
        "name": name,
        "arch": arch,
        "version": version,
        "description": description,
        "repository_uuids": repository_uuids,
        "use_latest": True
    }
    return await make_request(f"{INSIGHTS_BASE_URL}/content-sources/v1.0/templates", method="POST", json=payload)

if __name__ == "__main__":
    mcp.run(transport="stdio")
