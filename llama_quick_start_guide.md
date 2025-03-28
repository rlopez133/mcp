# 🦙 Llama Stack - Quick Start Guide using Conda + Anthropic 

This guide walks you through setting up and running the Llama Stack project on
your Mac.

# Setup Llama Stack

1. Create a llama config directory to hold llama-stack artifacts 

```bash
mkdir ~/.llama
```

2. Install Anaconda via brew

```bash
brew install anaconda3
```

3. Initialize Conda for bash 

```bash
/opt/homebrew/anaconda3/bin/conda init bash
```

4. Source your bash profile

```bash
source ~/.bash_profile
```

5. Clone the Llama Stack Repository and change directory

```bash
git clone git@github.com:meta-llama/llama-stack.git
cd llama-stack
```

6. Create and Activate a new Conda environment

```bash
conda create -n llama-stack-env
conda activate llama-stack-env
```

7. Install dependencies required to build llama-stack

```bash
conda install pip
pip install llama-stack emoji langdetect pythainlp
```

8. Build llama-stack using the `dev` template and `image-type` conda

```bash
llama stack build --template dev --image-type conda
```

9. Set your Anthropic API Key

```bash
export ANTHROPIC_API_KEY=<your_key>
```

10. Start your llama-stack environment

```bash
python -m llama_stack.distribution.server.server \
    --yaml-config ~/.llama/distributions/dev/dev-run.yaml
```

# Setting up your MCP Servers

To enable interaction between OpenShift and Ansible Automation Platform
(AAP) environments with the Llama Stack, we can convert these environments into
Model Context Protocol (MCP) servers. This integration allows Llama Stack agents
to utilize the functionalities provided by these environments as tools.

## Prerequisites 

Open a new terminal window and install Node.js using Homebrew. This will also
install npm and npx, which are required to run the MCP servers.

```bash
brew install node
```

## OpenShift/Kubernetes MCP Server

To integrate your OpenShift environment with Llama Stack, use the [Kubernetes MCP
Server](https://github.com/Flux159/mcp-server-kubernetes)

### Run the OpenShift/Kubernetes MCP Server

Export the `kubeconfig` of your OpenShift cluster to provide access

```bash
export KUBECONFIG=~/.kube/config
```

Run the following npx command to start the server via Supergateway, which wraps
the MCP stdio interface over SSE:

```bash
npx -y supergateway --port <port> --stdio "npx -y kubernetes-mcp-server@latest"
```

NOTE: Set `port` to the port you wish to map for your MCP Server.

## Ansible MCP Server

To enable your Ansible Automation Platform (AAP) environment to work with Llama
Stack, use the Ansible MCP Server included in this repository (ansible.py).

This server connects to your AAP instance and wraps it as a stdio-based MCP
server, which we expose using Supergateway.

In a new terminal window, run the following command:

```bash
npx -y supergateway --port <port> --stdio "AAP_TOKEN=<your_token> AAP_URL=https://<aap-url>/api/controller/v2 uv --directory /path/to/repo run ansible.py"
```

NOTE: Details to get your token are found in the README.md 

# Add MCP Servers to Llama Stack toolgroups

Within a new terminal, 

```bash
conda activate llama-stack-env
```

This ensures that all subsequent operations are executed within the appropriate
context where Llama Stack and its dependencies are available.

Install the llama-stack-client in order to list the toolgroups and add our MCP
servers.

```bash
pip install llama-stack-client
```

List the llama-stack tool groups

```bash
llama-stack-client toolgroups list
```
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━┓
┃ identifier                ┃ provider_id      ┃ args ┃ mcp_endpoint ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━┩
│ builtin::code_interpreter │ code-interpreter │ None │ None         │
│ builtin::rag              │ rag-runtime      │ None │ None         │
│ builtin::websearch        │ tavily-search    │ None │ None         │
└───────────────────────────┴──────────────────┴──────┴──────────────┘
```

To add the OpenShift/Kubernetes MCP server run the following command:

```
curl -X POST -H "Content-Type: application/json" --data '{ "provider_id" : "model-context-protocol", "toolgroup_id" : "mcp::kubernetes", "mcp_endpoint" : { "uri" : "http://localhost:8003/sse"}}' localhost:8321/v1/toolgroups
```

To add the Ansible MCP Server run the following command: 

```bash
curl -X POST -H "Content-Type: application/json" --data '{ "provider_id" : "model-context-protocol", "toolgroup_id" : "mcp::ansible", "mcp_endpoint" : { "uri" : "http://localhost:8004/sse"}}' localhost:8321/v1/toolgroups
```

NOTE: Change the port to the port used when you started your MCP Server.

## Verify the MCP Servers within llama-stack toolgroups

Verify the toolgroups are available

```bash
llama-stack-client toolgroups list
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ identifier                ┃ provider_id            ┃ args ┃ mcp_endpoint                                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ builtin::code_interpreter │ code-interpreter       │ None │ None                                         │
│ builtin::rag              │ rag-runtime            │ None │ None                                         │
│ builtin::websearch        │ tavily-search          │ None │ None                                         │
│ mcp::kubernetes           │ model-context-protocol │ None │ McpEndpoint(uri='http://localhost:8003/sse') │
│ mcp::ansible              │ model-context-protocol │ None │ McpEndpoint(uri='http://localhost:8004/sse') │
└───────────────────────────┴────────────────────────┴──────┴──────────────────────────────────────────────┘
```

# Setup your Llama Stack Client

In this repository, there is an `app.py` Streamlit application you can take
advantage of to chat with your AI. 

In order to run it, within a new terminal window:

1. Activate the conda environment

```bash
conda activate llama-stack-env
```


2. Install Streamlit

```bash
pip install streamlit
```

3. Run the `app.py` with Streamlit

```bash
streamlit run app.py
```

Video of the Streamlit app:

<a href="https://youtu.be/bwfjdeQHXHU"><img width="380" height="200" src="https://youtu.be/bwfjdeQHXHU" /></a>

