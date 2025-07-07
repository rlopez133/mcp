#!/usr/bin/env python3

import os
import httpx
import jwt
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - matching agentic-auth patterns
SERVER_NAME = "ansible-automation-platform"
SERVER_VERSION = "1.0.0"
SERVER_HOST = "localhost"
SERVER_PORT = 8001
SERVER_URI = f"http://{SERVER_HOST}:{SERVER_PORT}"

# Auth Server Configuration - must match agentic-auth setup
AUTH_SERVER_URI = "http://localhost:8002"  # The agentic-auth server
JWT_SECRET = os.getenv("JWT_SECRET", "demo-secret-key-change-in-production")

# AAP Configuration
AAP_URL = os.getenv("AAP_URL")
AAP_TOKEN = os.getenv("AAP_TOKEN")

if not AAP_TOKEN:
    raise ValueError("AAP_TOKEN is required")

# Headers for AAP API authentication
HEADERS = {
    "Authorization": f"Bearer {AAP_TOKEN}",
    "Content-Type": "application/json"
}

# Initialize FastMCP - matching agentic-auth patterns
mcp = FastMCP(
    name=SERVER_NAME,
    version=SERVER_VERSION
)

# Authentication functions - copied from agentic-auth/mcp/mcp_server.py
def verify_token_from_context(ctx: Context) -> dict:
    """Extract and verify JWT token from MCP context"""
    try:
        # Get Authorization header from request
        auth_header = ctx.request_context.request.headers.get("authorization")  # type: ignore
        logger.info(f"🔑 Auth header received: {auth_header[:50] if auth_header else 'None'}...")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.error("❌ Missing or invalid Authorization header")
            raise Exception("Missing or invalid Authorization header")
        
        token = auth_header.split(" ")[1]
        logger.info(f"🎫 JWT token: {token[:50]}...")
        
        payload = jwt.decode(
            token, 
            JWT_SECRET, 
            algorithms=["HS256"],
            options={"verify_aud": False},
            leeway=21600  # 6 hours leeway for clock skew
        )
        
        logger.info(f"📋 JWT payload: {payload}")
        
        # Validate audience - token must be for this MCP server
        if payload.get("aud") != SERVER_URI:
            logger.error(f"❌ Invalid audience: expected {SERVER_URI}, got {payload.get('aud')}")
            raise Exception(f"Invalid audience: expected {SERVER_URI}, got {payload.get('aud')}")
        
        # Validate issuer
        if payload.get("iss") != AUTH_SERVER_URI:
            logger.error(f"❌ Invalid issuer: expected {AUTH_SERVER_URI}, got {payload.get('iss')}")
            raise Exception(f"Invalid issuer: expected {AUTH_SERVER_URI}, got {payload.get('iss')}")
        
        logger.info(f"✅ Token validated for user: {payload.get('email')}")
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.error("❌ Token expired")
        raise Exception("Token expired")
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid token: {e}")
        raise Exception("Invalid token")

def check_scope(ctx: Context, required_scope: str) -> dict:
    """Check if user has required scope, return upgrade info if insufficient"""
    user = verify_token_from_context(ctx)
    user_scopes = user.get("scope", "").split()
    
    logger.info(f"🔐 Scope check: required='{required_scope}', user_scopes={user_scopes}, user_email={user.get('email')}")
    
    if required_scope not in user_scopes:
        error_info = {
            "error_type": "insufficient_scope",
            "error": f"Insufficient scope. Required: {required_scope}",
            "required_scope": required_scope,
            "user_scopes": user_scopes,
            "scope_upgrade_endpoint": f"{AUTH_SERVER_URI}/api/upgrade-scope",
            "scope_description": get_scope_description(required_scope),
            "upgrade_instructions": "Use the scope_upgrade_endpoint to request additional permissions"
        }
        logger.error(f"❌ Scope check failed: {error_info}")
        raise Exception(json.dumps(error_info))
    
    logger.info(f"✅ Scope check passed for {user.get('email')}")
    return user

def get_scope_description(scope: str) -> str:
    """Get human-readable description for a scope"""
    scope_descriptions = {
        "read:files": "Read access to Ansible resources (inventories, job templates, jobs)",
        "execute:commands": "Execute and manage Ansible operations (run jobs, create projects)"
    }
    return scope_descriptions.get(scope, f"Access to {scope}")

async def handle_scope_error(ctx: Context, error_msg: str) -> Dict[str, Any]:
    """Handle scope-related errors and return upgrade information"""
    try:
        error_data = json.loads(error_msg)
        if error_data.get("error_type") == "insufficient_scope":
            await ctx.info(f"Scope upgrade required: {error_data['required_scope']}")
            return {
                "success": False,
                "error_type": "insufficient_scope",
                "error": error_data["error"],
                "required_scope": error_data["required_scope"],
                "user_scopes": error_data["user_scopes"],
                "scope_upgrade_endpoint": error_data["scope_upgrade_endpoint"],
                "scope_description": error_data["scope_description"],
                "upgrade_instructions": error_data["upgrade_instructions"],
                "upgrade_example": {
                    "method": "POST",
                    "url": error_data["scope_upgrade_endpoint"],
                    "headers": {"Content-Type": "application/json"},
                    "body": {"scopes": [error_data["required_scope"]]}
                }
            }
    except (json.JSONDecodeError, KeyError):
        pass
    
    # Fallback for other errors
    return {
        "success": False,
        "error": error_msg
    }

# Helper function for AAP API requests
async def make_request(url: str, method: str = "GET", json: dict = None) -> Any:
    """Helper function to make authenticated API requests to AAP."""
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=HEADERS, json=json)
    if response.status_code not in [200, 201]:
        return f"Error {response.status_code}: {response.text}"
    return response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text

# AAP MCP Tools with authentication - using agentic-auth scope naming convention

@mcp.tool()
async def list_inventories(ctx: Context) -> Any:
    """
    List all inventories in Ansible Automation Platform.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to list all inventories.
    """
    try:
        # Verify authentication and scope
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} listing inventories")
        
        result = await make_request(f"{AAP_URL}/inventories/")
        
        # Add user context to successful results
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        elif isinstance(result, list):
            result = {"inventories": result, "authenticated_user": user.get('email')}
        else:
            result = {"data": result, "authenticated_user": user.get('email')}
            
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

# Server info and debugging tools - matching agentic-auth patterns

@mcp.tool()
async def get_server_info(ctx: Context) -> Dict[str, Any]:
    """
    Get server information and authentication status.
    
    **Required Scope:** Any valid token (no specific scope required)
    **Description:** Provides basic server information and user authentication details.
    """
    try:
        user = verify_token_from_context(ctx)
        await ctx.info(f"User {user.get('email')} requested server info")
        
        return {
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "server_uri": SERVER_URI,
            "auth_server_uri": AUTH_SERVER_URI,
            "aap_url": AAP_URL,
            "timestamp": datetime.now().isoformat(),
            "authenticated_user": user.get('email'),
            "user_scopes": user.get('scope', '').split(),
            "message": "Authentication successful - you have access to this AAP MCP server"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_oauth_metadata(ctx: Context) -> Dict[str, Any]:
    """
    Get OAuth 2.0 Protected Resource Metadata (RFC 9728).
    
    **Required Scope:** Any valid token (no specific scope required)
    **Description:** Returns OAuth 2.0 metadata for this protected resource.
    """
    try:
        user = verify_token_from_context(ctx)
        await ctx.info(f"User {user.get('email')} requested OAuth metadata")
        
        return {
            "resource": SERVER_URI,
            "authorization_servers": [AUTH_SERVER_URI],
            "scopes_supported": ["read:files", "execute:commands"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{SERVER_URI}/docs",
            "authenticated_user": user.get('email')
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def health_check(ctx: Context) -> Dict[str, Any]:
    """
    Perform a health check of the server.
    
    **Required Scope:** Any valid token (no specific scope required)
    **Description:** Verifies server health and user authentication status.
    """
    try:
        user = verify_token_from_context(ctx)
        await ctx.info(f"User {user.get('email')} requested health check")
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "aap_connection": "configured" if AAP_URL and AAP_TOKEN else "not configured",
            "checked_by": user.get('email')
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def list_tool_scopes(ctx: Context) -> Dict[str, Any]:
    """
    List all available tools and their required scopes.
    
    **Required Scope:** Any valid token (no specific scope required)
    **Description:** Provides a mapping of tools to their required scopes for authorization planning.
    """
    try:
        user = verify_token_from_context(ctx)
        await ctx.info(f"User {user.get('email')} requested tool scope information")
        
        tool_scopes = {
            # Read operations (read:files scope)
            "list_inventories": {
                "required_scope": "read:files",
                "description": "List all inventories in Ansible Automation Platform",
                "scope_description": "Read access to Ansible resources"
            },
            "get_inventory": {
                "required_scope": "read:files",
                "description": "Get details of a specific inventory by ID",
                "scope_description": "Read access to Ansible resources"
            },
            "job_status": {
                "required_scope": "read:files",
                "description": "Check the status of a job by ID",
                "scope_description": "Read access to Ansible resources"
            },
            "job_logs": {
                "required_scope": "read:files",
                "description": "Retrieve logs for a job",
                "scope_description": "Read access to Ansible resources"
            },
            "list_inventory_sources": {
                "required_scope": "read:files",
                "description": "List all inventory sources",
                "scope_description": "Read access to Ansible resources"
            },
            "get_inventory_source": {
                "required_scope": "read:files",
                "description": "Get details of a specific inventory source",
                "scope_description": "Read access to Ansible resources"
            },
            "list_job_templates": {
                "required_scope": "read:files",
                "description": "List all job templates",
                "scope_description": "Read access to Ansible resources"
            },
            "get_job_template": {
                "required_scope": "read:files",
                "description": "Retrieve details of a specific job template",
                "scope_description": "Read access to Ansible resources"
            },
            "list_jobs": {
                "required_scope": "read:files",
                "description": "List all jobs",
                "scope_description": "Read access to Ansible resources"
            },
            "list_recent_jobs": {
                "required_scope": "read:files",
                "description": "List jobs from the last specified hours",
                "scope_description": "Read access to Ansible resources"
            },
            
            # Execute and management operations (execute:commands scope)
            "run_job": {
                "required_scope": "execute:commands",
                "description": "Run a job template by ID, optionally with extra_vars",
                "scope_description": "Execute and manage Ansible operations"
            },
            "sync_inventory_source": {
                "required_scope": "execute:commands",
                "description": "Manually trigger a sync for an inventory source",
                "scope_description": "Execute and manage Ansible operations"
            },
            "create_project": {
                "required_scope": "execute:commands",
                "description": "Create a new project in Ansible Automation Platform",
                "scope_description": "Execute and manage Ansible operations"
            },
            "create_job_template": {
                "required_scope": "execute:commands",
                "description": "Create a new job template",
                "scope_description": "Execute and manage Ansible operations"
            },
            "create_inventory_source": {
                "required_scope": "execute:commands",
                "description": "Create a dynamic inventory source",
                "scope_description": "Execute and manage Ansible operations"
            },
            "update_inventory_source": {
                "required_scope": "execute:commands",
                "description": "Update an existing inventory source",
                "scope_description": "Execute and manage Ansible operations"
            },
            "delete_inventory_source": {
                "required_scope": "execute:commands",
                "description": "Delete an inventory source",
                "scope_description": "Execute and manage Ansible operations"
            },
            "create_inventory": {
                "required_scope": "execute:commands",
                "description": "Create an inventory",
                "scope_description": "Execute and manage Ansible operations"
            },
            "delete_inventory": {
                "required_scope": "execute:commands",
                "description": "Delete an inventory",
                "scope_description": "Execute and manage Ansible operations"
            },
            "associate_credential_with_template": {
                "required_scope": "execute:commands",
                "description": "Associate a credential with a job template",
                "scope_description": "Execute and manage Ansible operations"
            },
            "update_job_template": {
                "required_scope": "execute:commands",
                "description": "Update an existing job template",
                "scope_description": "Execute and manage Ansible operations"
            },
            "delete_job_template": {
                "required_scope": "execute:commands",
                "description": "Delete a job template",
                "scope_description": "Execute and manage Ansible operations"
            },
            
            # Server info tools (no specific scope required)
            "get_server_info": {
                "required_scope": "none",
                "description": "Get server information and authentication status",
                "scope_description": "Any valid token (no specific scope required)"
            },
            "get_oauth_metadata": {
                "required_scope": "none",
                "description": "Get OAuth 2.0 Protected Resource Metadata",
                "scope_description": "Any valid token (no specific scope required)"
            },
            "health_check": {
                "required_scope": "none",
                "description": "Perform a health check of the server",
                "scope_description": "Any valid token (no specific scope required)"
            },
            "list_tool_scopes": {
                "required_scope": "none",
                "description": "List all available tools and their required scopes",
                "scope_description": "Any valid token (no specific scope required)"
            }
        }
        
        return {
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "available_scopes": ["read:files", "execute:commands"],
            "tool_scope_mapping": tool_scopes,
            "user_scopes": user.get('scope', '').split(),
            "total_tools": len(tool_scopes),
            "timestamp": datetime.now().isoformat(),
            "checked_by": user.get('email')
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    logger.info(f"Starting {SERVER_NAME} v{SERVER_VERSION}")
    logger.info(f"Server URI: {SERVER_URI}")
    logger.info(f"Auth server: {AUTH_SERVER_URI}")
    logger.info(f"AAP URL: {AAP_URL}")
    logger.info("🔐 Authentication enabled - all tools require valid JWT tokens")
    logger.info("📋 Available scopes: read:files (read operations), execute:commands (execute & manage)")
    logger.info("🔧 Available tools:")
    logger.info("   Read (read:files): list_inventories, get_inventory, job_status, job_logs, list_job_templates, etc.")
    logger.info("   Execute & Manage (execute:commands): run_job, create_project, create_job_template, etc.")
    logger.info("   Info (no scope): get_server_info, health_check, list_tool_scopes")
    
    # Run with stdio transport to integrate with agentic-auth
    mcp.run(transport="stdio")(ctx, str(e))

@mcp.tool()
async def get_inventory(ctx: Context, inventory_id: str) -> Any:
    """
    Get details of a specific inventory by ID.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to inventory details.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} getting inventory {inventory_id}")
        
        result = await make_request(f"{AAP_URL}/inventories/{inventory_id}/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def run_job(ctx: Context, template_id: int, extra_vars: dict = {}) -> Any:
    """
    Run a job template by ID, optionally with extra_vars.
    
    **Required Scope:** execute:ansible
    **Description:** Allows execution of Ansible job templates and playbooks.
    """
    try:
        user = check_scope(ctx, "execute:ansible")
        await ctx.info(f"User {user.get('email')} running job template {template_id}")
        
        result = await make_request(
            f"{AAP_URL}/job_templates/{template_id}/launch/", 
            method="POST", 
            json={"extra_vars": extra_vars}
        )
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
            result["template_id"] = template_id
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def job_status(ctx: Context, job_id: int) -> Any:
    """
    Check the status of a job by ID.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to job status and details.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} checking job status {job_id}")
        
        result = await make_request(f"{AAP_URL}/jobs/{job_id}/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def job_logs(ctx: Context, job_id: int) -> str:
    """
    Retrieve logs for a job.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to job execution logs.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} getting job logs {job_id}")
        
        result = await make_request(f"{AAP_URL}/jobs/{job_id}/stdout/")
        
        return {
            "job_id": job_id,
            "logs": result,
            "authenticated_user": user.get('email')
        }
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def create_project(
    ctx: Context,
    name: str,
    organization_id: int,
    source_control_url: str,
    source_control_type: str = "git",
    description: str = "",
    execution_environment_id: int = None,
    content_signature_validation_credential_id: int = None,
    source_control_branch: str = "",
    source_control_refspec: str = "",
    source_control_credential_id: int = None,
    clean: bool = False,
    update_revision_on_launch: bool = False,
    delete: bool = False,
    allow_branch_override: bool = False,
    track_submodules: bool = False,
) -> Any:
    """
    Create a new project in Ansible Automation Platform.
    
    **Required Scope:** manage:ansible
    **Description:** Allows creation and management of projects in AAP.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} creating project '{name}'")

        payload = {
            "name": name,
            "description": description,
            "organization": organization_id,
            "scm_type": source_control_type.lower(),
            "scm_url": source_control_url,
            "scm_branch": source_control_branch,
            "scm_refspec": source_control_refspec,
            "scm_clean": clean,
            "scm_delete_on_update": delete,
            "scm_update_on_launch": update_revision_on_launch,
            "allow_override": allow_branch_override,
            "scm_track_submodules": track_submodules,
        }

        if execution_environment_id:
            payload["execution_environment"] = execution_environment_id
        if content_signature_validation_credential_id:
            payload["signature_validation_credential"] = content_signature_validation_credential_id
        if source_control_credential_id:
            payload["credential"] = source_control_credential_id

        result = await make_request(f"{AAP_URL}/projects/", method="POST", json=payload)
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def create_job_template(
    ctx: Context,
    name: str,
    project_id: int,
    playbook: str,
    inventory_id: int,
    job_type: str = "run",
    description: str = "",
    credential_id: int = None,
    execution_environment_id: int = None,
    labels: list[str] = None,
    forks: int = 0,
    limit: str = "",
    verbosity: int = 0,
    timeout: int = 0,
    job_tags: list[str] = None,
    skip_tags: list[str] = None,
    extra_vars: dict = None,
    privilege_escalation: bool = False,
    concurrent_jobs: bool = False,
    provisioning_callback: bool = False,
    enable_webhook: bool = False,
    prevent_instance_group_fallback: bool = False,
    survey_spec: dict = None,
) -> Any:
    """
    Create a new job template in Ansible Automation Platform.
    
    **Required Scope:** manage:ansible
    **Description:** Allows creation and management of job templates.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} creating job template '{name}'")

        payload = {
            "name": name,
            "description": description,
            "job_type": job_type,
            "project": project_id,
            "playbook": playbook,
            "inventory": inventory_id,
            "forks": forks,
            "limit": limit,
            "verbosity": verbosity,
            "timeout": timeout,
            "ask_variables_on_launch": bool(extra_vars),
            "ask_tags_on_launch": bool(job_tags),
            "ask_skip_tags_on_launch": bool(skip_tags),
            "ask_credential_on_launch": credential_id is None,
            "ask_execution_environment_on_launch": execution_environment_id is None,
            "ask_labels_on_launch": labels is None,
            "ask_inventory_on_launch": False,
            "ask_job_type_on_launch": False,
            "become_enabled": privilege_escalation,
            "allow_simultaneous": concurrent_jobs,
            "scm_branch": "",
            "webhook_service": "github" if enable_webhook else "",
            "prevent_instance_group_fallback": prevent_instance_group_fallback,
        }

        if credential_id:
            payload["credential"] = credential_id
        if execution_environment_id:
            payload["execution_environment"] = execution_environment_id
        if labels:
            payload["labels"] = labels
        if job_tags:
            payload["job_tags"] = job_tags
        if skip_tags:
            payload["skip_tags"] = skip_tags
        if extra_vars:
            payload["extra_vars"] = extra_vars
        if survey_spec:
            payload["survey_spec"] = survey_spec

        result = await make_request(f"{AAP_URL}/job_templates/", method="POST", json=payload)
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def list_inventory_sources(ctx: Context) -> Any:
    """
    List all inventory sources in Ansible Automation Platform.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to inventory sources.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} listing inventory sources")
        
        result = await make_request(f"{AAP_URL}/inventory_sources/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def get_inventory_source(ctx: Context, inventory_source_id: int) -> Any:
    """
    Get details of a specific inventory source.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to inventory source details.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} getting inventory source {inventory_source_id}")
        
        result = await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def create_inventory_source(
    ctx: Context,
    name: str,
    inventory_id: int,
    source: str,
    credential_id: int,
    source_vars: dict = None,
    update_on_launch: bool = True,
    timeout: int = 0,
) -> Any:
    """
    Create a dynamic inventory source.
    
    **Required Scope:** manage:ansible
    **Description:** Create dynamic inventory sources with proper validation.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} creating inventory source '{name}'")
        
        valid_sources = [
            "file", "constructed", "scm", "ec2", "gce", "azure_rm", "vmware", "satellite6", "openstack", 
            "rhv", "controller", "insights", "terraform", "openshift_virtualization"
        ]
        
        if source not in valid_sources:
            return {
                "success": False,
                "error": f"Invalid source type '{source}'. Please select from: {', '.join(valid_sources)}",
                "authenticated_user": user.get('email')
            }
        
        if not credential_id:
            return {
                "success": False,
                "error": "Credential is required to create an inventory source.",
                "authenticated_user": user.get('email')
            }
        
        payload = {
            "name": name,
            "inventory": inventory_id,
            "source": source,
            "credential": credential_id,
            "source_vars": source_vars,
            "update_on_launch": update_on_launch,
            "timeout": timeout,
        }
        
        result = await make_request(f"{AAP_URL}/inventory_sources/", method="POST", json=payload)
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def update_inventory_source(ctx: Context, inventory_source_id: int, update_data: dict) -> Any:
    """
    Update an existing inventory source.
    
    **Required Scope:** manage:ansible
    **Description:** Update inventory source configuration.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} updating inventory source {inventory_source_id}")
        
        result = await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/", method="PATCH", json=update_data)
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def delete_inventory_source(ctx: Context, inventory_source_id: int) -> Any:
    """
    Delete an inventory source.
    
    **Required Scope:** manage:ansible
    **Description:** Delete inventory sources with proper authorization.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} deleting inventory source {inventory_source_id}")
        
        result = await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/", method="DELETE")
        
        return {
            "success": True,
            "message": f"Inventory source {inventory_source_id} deleted successfully",
            "authenticated_user": user.get('email')
        }
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def sync_inventory_source(ctx: Context, inventory_source_id: int) -> Any:
    """
    Manually trigger a sync for an inventory source.
    
    **Required Scope:** execute:ansible
    **Description:** Trigger inventory synchronization jobs.
    """
    try:
        user = check_scope(ctx, "execute:ansible")
        await ctx.info(f"User {user.get('email')} syncing inventory source {inventory_source_id}")
        
        result = await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/update/", method="POST")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def create_inventory(
    ctx: Context,
    name: str,
    organization_id: int,
    description: str = "",
    kind: str = "",
    host_filter: str = "",
    variables: dict = None,
    prevent_instance_group_fallback: bool = False,
) -> Any:
    """
    Create an inventory in Ansible Automation Platform.
    
    **Required Scope:** manage:ansible
    **Description:** Create new inventories with proper validation.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} creating inventory '{name}'")
        
        payload = {
            "name": name,
            "organization": organization_id,
            "description": description,
            "kind": kind,
            "host_filter": host_filter,
            "variables": variables,
            "prevent_instance_group_fallback": prevent_instance_group_fallback,
        }
        
        result = await make_request(f"{AAP_URL}/inventories/", method="POST", json=payload)
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def delete_inventory(ctx: Context, inventory_id: int) -> Any:
    """
    Delete an inventory from Ansible Automation Platform.
    
    **Required Scope:** manage:ansible
    **Description:** Delete inventories with proper authorization.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} deleting inventory {inventory_id}")
        
        result = await make_request(f"{AAP_URL}/inventories/{inventory_id}/", method="DELETE")
        
        return {
            "success": True,
            "message": f"Inventory {inventory_id} deleted successfully",
            "authenticated_user": user.get('email')
        }
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def associate_credential_with_template(ctx: Context, template_id: int, credential_id: int) -> Any:
    """
    Associate a credential with an existing job template.
    
    **Required Scope:** manage:ansible
    **Description:** Manage job template credentials.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} associating credential {credential_id} with template {template_id}")
        
        result = await make_request(
            f"{AAP_URL}/job_templates/{template_id}/credentials/", 
            method="POST", 
            json={"id": credential_id}
        )
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def list_job_templates(ctx: Context) -> Any:
    """
    List all job templates available in Ansible Automation Platform.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to job templates.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} listing job templates")
        
        result = await make_request(f"{AAP_URL}/job_templates/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def get_job_template(ctx: Context, template_id: int) -> Any:
    """
    Retrieve details of a specific job template.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to job template details.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} getting job template {template_id}")
        
        result = await make_request(f"{AAP_URL}/job_templates/{template_id}/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def update_job_template(ctx: Context, template_id: int, update_data: dict) -> Any:
    """
    Update an existing job template.
    
    **Required Scope:** manage:ansible
    **Description:** Update job template configuration.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} updating job template {template_id}")
        
        result = await make_request(f"{AAP_URL}/job_templates/{template_id}/", method="PATCH", json=update_data)
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def delete_job_template(ctx: Context, template_id: int) -> Any:
    """
    Delete a job template from Ansible Automation Platform.
    
    **Required Scope:** manage:ansible
    **Description:** Delete job templates with proper authorization.
    """
    try:
        user = check_scope(ctx, "manage:ansible")
        await ctx.info(f"User {user.get('email')} deleting job template {template_id}")
        
        result = await make_request(f"{AAP_URL}/job_templates/{template_id}/", method="DELETE")
        
        return {
            "success": True,
            "message": f"Job template {template_id} deleted successfully",
            "authenticated_user": user.get('email')
        }
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def list_jobs(ctx: Context) -> Any:
    """
    List all jobs available in Ansible Automation Platform.
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to job history.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} listing jobs")
        
        result = await make_request(f"{AAP_URL}/jobs/")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
        
        return result
        
    except Exception as e:
        return await handle_scope_error(ctx, str(e))

@mcp.tool()
async def list_recent_jobs(ctx: Context, hours: int = 24) -> Any:
    """
    List all jobs executed in the last specified hours (default 24 hours).
    
    **Required Scope:** read:ansible
    **Description:** Provides read-only access to recent job execution history.
    """
    try:
        user = check_scope(ctx, "read:ansible")
        await ctx.info(f"User {user.get('email')} listing recent jobs from last {hours} hours")
        
        time_filter = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
        result = await make_request(f"{AAP_URL}/jobs/?created__gte={time_filter}")
        
        if isinstance(result, dict):
            result["authenticated_user"] = user.get('email')
            result["time_filter"] = time_filter
        
        return result
        
    except Exception as e:
        return await handle_scope_error
