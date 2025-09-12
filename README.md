# Setup of the Environment for the AI Powered Ansible & OpenShift Automation with Model Context Protocols (MCP) Servers

## Overview

This guide will walk you through setting up the MCP Servers + Claude Desktop portions of the demo that focused on using Claude Desktop to interact with your Ansible Automation Platform and OpenShift Cluster environments. 

## Prerequisites

Ensure you have the following installed. 

### Required
- An Ansible Automation Platform (AAP) environment
- An OpenShift Cluster with OpenShift Virtualization
- [Claude Desktop](https://claude.ai/download) installed on your laptop (Pro Plan required for best results)
- Python 3.10 or higher installed on your laptop
- Ensure you are authenticated with your OpenShift cluster (e.g. exporting kubeconfig)

## Step One: Setup your laptop environment

Install `uv` and setup your Python project and environment.

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install [jbang](https://www.jbang.dev/download/) which will be used when using the Kubernetes MCP Server. (jbang needs to be installed globally, recommend using the homebrew install pattern. If you install it locally (the curl pattern), Claude won't be able to access it).

Restart your terminal to ensure that the `uv` and `jbang` command are now available.

## Step Two: Create and Setup your Project

```
# Create a new directory for our project
uv init ansible
cd ansible

# Create virtual environment and activate it
uv venv
source .venv/bin/activate

# Install dependencies
uv add "mcp[cli]" httpx

# Create our server file
touch ansible.py
```

## Step 3 Building your Ansible Automation Controller MCP Server

This is the MCP Server I used to interact with my automation controller. Feel free to copy/paste this into your `ansible.py` file.

Note: to connect to self-signed SSL, use edit the async client to be https.AsyncClient(verify=False)

```
import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Any

# Environment variables for authentication
AAP_URL = os.getenv("AAP_URL")
AAP_TOKEN = os.getenv("AAP_TOKEN")

if not AAP_TOKEN:
    raise ValueError("AAP_TOKEN is required")

# Headers for API authentication
HEADERS = {
    "Authorization": f"Bearer {AAP_TOKEN}",
    "Content-Type": "application/json"
}

# Initialize FastMCP
mcp = FastMCP("ansible")

async def make_request(url: str, method: str = "GET", json: dict = None) -> Any:
    """Helper function to make authenticated API requests to AAP."""
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=HEADERS, json=json)
    if response.status_code not in [200, 201]:
        return f"Error {response.status_code}: {response.text}"
    return response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text

@mcp.tool()
async def list_inventories() -> Any:
    """List all inventories in Ansible Automation Platform."""
    return await make_request(f"{AAP_URL}/inventories/")

@mcp.tool()
async def get_inventory(inventory_id: str) -> Any:
    """Get details of a specific inventory by ID."""
    return await make_request(f"{AAP_URL}/inventories/{inventory_id}/")

@mcp.tool()
async def run_job(template_id: int, extra_vars: dict = {}) -> Any:
    """Run a job template by ID, optionally with extra_vars."""
    return await make_request(f"{AAP_URL}/job_templates/{template_id}/launch/", method="POST", json={"extra_vars": extra_vars})

@mcp.tool()
async def job_status(job_id: int) -> Any:
    """Check the status of a job by ID."""
    return await make_request(f"{AAP_URL}/jobs/{job_id}/")

@mcp.tool()
async def job_logs(job_id: int) -> str:
    """Retrieve logs for a job."""
    return await make_request(f"{AAP_URL}/jobs/{job_id}/stdout/")

@mcp.tool()
async def create_project(
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
    """Create a new project in Ansible Automation Platform."""

    payload = {
        "name": name,
        "description": description,
        "organization": organization_id,
        "scm_type": source_control_type.lower(),  # Git is default
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

    return await make_request(f"{AAP_URL}/projects/", method="POST", json=payload)

@mcp.tool()
async def create_job_template(
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
) -> Any:
    """Create a new job template in Ansible Automation Platform."""

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
        "ask_inventory_on_launch": False,  # Inventory is required, so not prompting
        "ask_job_type_on_launch": False,  # Job type is required, so not prompting
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

    return await make_request(f"{AAP_URL}/job_templates/", method="POST", json=payload)

@mcp.tool()
async def list_inventory_sources() -> Any:
    """List all inventory sources in Ansible Automation Platform."""
    return await make_request(f"{AAP_URL}/inventory_sources/")

@mcp.tool()
async def get_inventory_source(inventory_source_id: int) -> Any:
    """Get details of a specific inventory source."""
    return await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/")

@mcp.tool()
async def create_inventory_source(
    name: str,
    inventory_id: int,
    source: str,
    credential_id: int,
    source_vars: dict = None,
    update_on_launch: bool = True,
    timeout: int = 0,
) -> Any:
    """Create a dynamic inventory source. Claude will ask for the source type and credential before proceeding."""
    valid_sources = [
        "file", "constructed", "scm", "ec2", "gce", "azure_rm", "vmware", "satellite6", "openstack", 
        "rhv", "controller", "insights", "terraform", "openshift_virtualization"
    ]
    
    if source not in valid_sources:
        return f"Error: Invalid source type '{source}'. Please select from: {', '.join(valid_sources)}"
    
    if not credential_id:
        return "Error: Credential is required to create an inventory source."
    
    payload = {
        "name": name,
        "inventory": inventory_id,
        "source": source,
        "credential": credential_id,
        "source_vars": source_vars,
        "update_on_launch": update_on_launch,
        "timeout": timeout,
    }
    return await make_request(f"{AAP_URL}/inventory_sources/", method="POST", json=payload)

@mcp.tool()
async def update_inventory_source(inventory_source_id: int, update_data: dict) -> Any:
    """Update an existing inventory source."""
    return await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/", method="PATCH", json=update_data)

@mcp.tool()
async def delete_inventory_source(inventory_source_id: int) -> Any:
    """Delete an inventory source."""
    return await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/", method="DELETE")

@mcp.tool()
async def sync_inventory_source(inventory_source_id: int) -> Any:
    """Manually trigger a sync for an inventory source."""
    return await make_request(f"{AAP_URL}/inventory_sources/{inventory_source_id}/update/", method="POST")

@mcp.tool()
async def create_inventory(
    name: str,
    organization_id: int,
    description: str = "",
    kind: str = "",
    host_filter: str = "",
    variables: dict = None,
    prevent_instance_group_fallback: bool = False,
) -> Any:
    """Create an inventory in Ansible Automation Platform."""
    payload = {
        "name": name,
        "organization": organization_id,
        "description": description,
        "kind": kind,
        "host_filter": host_filter,
        "variables": variables,
        "prevent_instance_group_fallback": prevent_instance_group_fallback,
    }
    return await make_request(f"{AAP_URL}/inventories/", method="POST", json=payload)

@mcp.tool()
async def delete_inventory(inventory_id: int) -> Any:
    """Delete an inventory from Ansible Automation Platform."""
    return await make_request(f"{AAP_URL}/inventories/{inventory_id}/", method="DELETE")

@mcp.tool()
async def list_job_templates() -> Any:
    """List all job templates available in Ansible Automation Platform."""
    return await make_request(f"{AAP_URL}/job_templates/")

@mcp.tool()
async def get_job_template(template_id: int) -> Any:
    """Retrieve details of a specific job template."""
    return await make_request(f"{AAP_URL}/job_templates/{template_id}/")

@mcp.tool()
async def list_jobs() -> Any:
    """List all jobs available in Ansible Automation Platform."""
    return await make_request(f"{AAP_URL}/jobs/")

@mcp.tool()
async def list_recent_jobs(hours: int = 24) -> Any:
    """List all jobs executed in the last specified hours (default 24 hours)."""
    from datetime import datetime, timedelta
    
    time_filter = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
    return await make_request(f"{AAP_URL}/jobs/?created__gte={time_filter}")

if __name__ == "__main__":
    mcp.run(transport="stdio")

```

## Step 4: Configuring Claude Desktop to use your MCP Servers

In my particular case, I want to take advantage of two MCP Servers: the Ansible MCP Server above and the Kubernetes MCP Server that I found within the [quarkus-mcp-servers](https://github.com/quarkiverse/quarkus-mcp-servers/tree/main/kubernetes) Git repo

Open the `claude_desktop_config.json` , which on MacOS is located at

```
~/Library/Application\ Support/Claude/claude_desktop_config.json
```

```
{
  "mcpServers": {
    "ansible": {
        "command": "/absolute/path/to/uv",
        "args": [
            "--directory",
            "/absolute/path/to/ansible_mcp",
            "run",
            "ansible.py"
        ],
        "env": {
            "AAP_TOKEN": "<aap-token>",
            "AAP_URL": "https://<aap-url>/api/controller/v2"
        }
    },
    "kubernetes": {
      "command": "jbang",
      "args": [
        "--quiet",
        "https://github.com/quarkiverse/quarkus-mcp-servers/blob/main/kubernetes/src/main/java/io/quarkiverse/mcp/servers/kubernetes/MCPServerKubernetes.java"
      ]
    }
  }
}
```
Save the file.

WARNING: Absolute path to your `uv` binary is required. Do a `which uv` on your system to get the full path. 

NOTE: If you need to create the AAP_TOKEN, go to the AAP Dashboard, select Access Management -> Users -> <your_user> -> Tokens -> Create token -> Select the Scope dropdown and select 'Write' and click Create token.

## Step 5: Re-Launch Claude Desktop 

If you already had Claude Desktop open, relaunch it, otherwise make sure Claude Desktop is picking up the MCP servers. You can verify this by ensuring the hammer icon is launched.

![Screenshot 2025-02-26 at 3 46 30 PM](https://github.com/user-attachments/assets/064e2edb-dfaa-4250-8a82-d8e59c21644f)

NOTE: The number next to the hammer will vary based up on the amount of MCP tools available. 

Once you click on the hammer icon, you can see a list of tools. Below is an example.

![Screenshot 2025-02-26 at 3 50 23 PM](https://github.com/user-attachments/assets/78ae7be0-e1a6-4fbb-8520-4d57a6563bbe)

## Step 6: Test your Environment

Now with everything setup, see if you can interact with your Ansible Automation Platform and OpenShift cluster. 

Feel free to ask it questions such as:

* How many Job Templates are available?
* How many VMs are on my OpenShift cluster?

NOTE: It is very likely you will need to take advantage of the Claude Desktop Pro Plan in order to get the full functionality. 

## References

[Claude Desktop Quickstart for Server Developers](https://modelcontextprotocol.io/quickstart/server)


## BONUS: Adding Event Driven Ansible MCP Server

If you have setup Event Driven Ansible, you can take advantage of the Event Driven Ansible MCP Server below. The instructions are similar to the above. 

* Create an `eda.py` and store it in your `/absolute/path/to/ansible_mcp`
* Update your `claude_desktop_config.json`
* Restart your Claude Desktop and verify the hammer has picked up your new MCP tools

The two files are listed below for easy copy/paste.

### claude_desktop_config.json
```
{
  "mcpServers": {
    "ansible": {
        "command": "/absolute/path/to/uv",
        "args": [
            "--directory",
            "/absolute/path/to/ansible_mcp",
            "run",
            "ansible.py"
        ],
        "env": {
            "AAP_TOKEN": "<aap-token>",
            "AAP_URL": "https://<aap-url>/api/controller/v2"
        }
    },
    "kubernetes": {
      "command": "jbang",
      "args": [
        "--quiet",
        "https://github.com/quarkiverse/quarkus-mcp-servers/blob/main/kubernetes/src/main/java/io/quarkiverse/mcp/servers/kubernetes/MCPServerKubernetes.java"
      ]
    },
    "eda": {
        "command": "/absolute/path/to/uv",
        "args": [
            "--directory",
            "/absolute/path/to/ansible_mcp",
            "run",
            "eda.py"
        ],
        "env": {
            "EDA_TOKEN": "<eda-token-can-be-same-as-aap-token>",
            "EDA_URL": "https://<aap-url>/api/eda/v1"
        }
    }
  }
}
```

WARNING: Absolute path to your `uv` binary is required. Do a `which uv` on your system to get the full path. 

NOTE: An EDA Token can be generated from the AAP Dashboard. 

### eda.py MCP Server 

```
import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional, Any, Dict

# Environment variables for authentication
EDA_URL = os.getenv("EDA_URL")
EDA_TOKEN = os.getenv("EDA_TOKEN")

if not EDA_TOKEN:
    raise ValueError("EDA_TOKEN is required")

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
```

