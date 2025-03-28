import streamlit as st
from llama_stack_client import LlamaStackClient
from llama_stack_client.lib.agents.agent import Agent
from llama_stack_client.types.agent_create_params import AgentConfig
import os
import json
from datetime import datetime

# Initialize LlamaStack client
base_url = os.getenv("BASE_URL", "http://localhost:8321") 
client = LlamaStackClient(base_url=base_url)

# Page configuration
st.set_page_config(
    page_title="Llama-stack Chat",
    page_icon="🦙",
    layout="wide",
)

# Styling for code blocks
st.markdown("""
<style>
    code {
        background-color: #f0f2f6;
        border-radius: 3px;
        padding: 0.2em 0.4em;
    }
    pre {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 0.5em;
    }
    .chat-message {
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .blinking-cursor {
        animation: blink 1s step-end infinite;
    }
    @keyframes blink {
        50% { opacity: 0; }
    }
</style>
""", unsafe_allow_html=True)

# Get providers with valid credentials (simplified approach)
@st.cache_data(ttl=300)
def get_configured_providers():
    try:
        # This is a simplified approach that assumes Anthropic is configured
        # In a real implementation, you would check LLama Stack's configuration
        return ["anthropic"]
    except Exception as e:
        st.error(f"Error checking configured providers: {e}")
        return ["anthropic"]  # Fallback to Anthropic

# Get available models from configured providers
@st.cache_data(ttl=300)
def get_available_models():
    try:
        models = client.models.list()
        configured_providers = get_configured_providers()
        
        # Filter for LLM models from configured providers
        available_models = [
            model.identifier 
            for model in models 
            if model.model_type == "llm" and model.provider_id in configured_providers
        ]
        
        return available_models
    except Exception as e:
        st.error(f"Error fetching models: {e}")
        return ["anthropic/claude-3-7-sonnet-latest"]  # Fallback default

# Get all available toolgroups
@st.cache_data(ttl=300)
def get_all_toolgroups():
    try:
        toolgroups = client.toolgroups.list()
        return [toolgroup.identifier for toolgroup in toolgroups]
    except Exception as e:
        st.error(f"Error fetching toolgroups: {e}")
        return ["mcp::ansible"]  # Fallback default

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "system_instruction" not in st.session_state:
    st.session_state.system_instruction = "You are a helpful assistant that can access various tools to help the user."
if "show_save_dialog" not in st.session_state:
    st.session_state.show_save_dialog = False
if "saved_chats" not in st.session_state:
    st.session_state.saved_chats = "{}"
if "chat_updated" not in st.session_state:
    st.session_state.chat_updated = False

# Function to check if there are messages
def has_messages():
    return len(st.session_state.messages) > 0

# Streamlit UI
st.title("Llama-stack Chat")
st.markdown("Chat with LLama Stack and its toolgroups")

# Sidebar configurations
with st.sidebar:
    st.header("Configuration")
    
    # Model selection
    available_models = get_available_models()
    selected_model = st.selectbox("Select Model", available_models)
    
    # Get all toolgroups automatically and display as collapsible
    all_toolgroups = get_all_toolgroups()
    with st.expander(f"{len(all_toolgroups)} Toolgroups Loaded"):
        for toolgroup in all_toolgroups:
            st.caption(f"• {toolgroup}")
    
    # System instructions
    with st.expander("System Instructions", expanded=False):
        new_instruction = st.text_area(
            "Customize how the assistant behaves:", 
            st.session_state.system_instruction,
            height=100
        )
        if new_instruction != st.session_state.system_instruction:
            st.session_state.system_instruction = new_instruction
            st.toast("System instructions updated")
    
    # Collapsible Query Context section
    with st.expander("Query Context", expanded=False):
        query_context = st.text_area("Add background information for this query:", "", height=150)
        st.caption("This information will be included with each of your queries but won't be visible in the chat.")
    
    # Temperature in collapsible
    with st.expander("Temperature", expanded=False):
        temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
        top_p = st.slider("Top P", min_value=0.0, max_value=1.0, value=0.9, step=0.1)
    
    # Chat history management
    st.header("Chat Management")
    
    # Using two separate buttons instead of columns for better visibility
    clear_col, save_col = st.columns(2)
    
    # Clear chat button
    with clear_col:
        if st.button("🗑️ Clear Chat", key="clear_chat"):
            st.session_state.messages = []
            st.session_state.chat_updated = True
            st.rerun()
    
    # Save button - disabled when no messages
    with save_col:
        if st.button("💾 Save Chat", key="save_chat", disabled=not has_messages()):
            st.session_state.show_save_dialog = True
    
    # Save dialog - shown when save button is clicked
    if st.session_state.show_save_dialog:
        st.text_input("Conversation name:", key="save_name")
        save_confirm, cancel = st.columns(2)
        
        with save_confirm:
            if st.button("Confirm Save", key="confirm_save"):
                if st.session_state.save_name:
                    saved_chats = json.loads(st.session_state.saved_chats)
                    saved_chats[st.session_state.save_name] = st.session_state.messages
                    st.session_state.saved_chats = json.dumps(saved_chats)
                    st.session_state.show_save_dialog = False
                    st.toast(f"Saved conversation: {st.session_state.save_name}")
                    st.rerun()
                else:
                    st.warning("Please enter a name for the conversation")
        
        with cancel:
            if st.button("Cancel", key="cancel_save"):
                st.session_state.show_save_dialog = False
                st.rerun()
    
    # Export chat button - disabled when no messages
    if st.button("📥 Export Chat", key="export_chat", disabled=not has_messages()):
        chat_export = ""
        for msg in st.session_state.messages:
            prefix = "🧑" if msg["role"] == "user" else "🤖"
            chat_export += f"{prefix} **{msg['role'].capitalize()}**: {msg['content']}\n\n"
        
        # Create download link
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_export_{timestamp}.md"
        st.download_button(
            label="Download Chat",
            data=chat_export,
            file_name=filename,
            mime="text/markdown",
            key="download_chat"
        )
    
    # Load saved conversations
    st.header("Saved Conversations")
    
    # Load saved conversation
    saved_chats = json.loads(st.session_state.saved_chats)
    if saved_chats:
        chat_names = list(saved_chats.keys())
        selected_chat = st.selectbox("Select a saved conversation:", [""] + chat_names)
        if selected_chat and st.button("📂 Load Conversation"):
            st.session_state.messages = saved_chats[selected_chat]
            st.session_state.chat_updated = True
            st.toast(f"Loaded conversation: {selected_chat}")
            st.rerun()
    else:
        st.caption("No saved conversations yet")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # Apply syntax highlighting for code blocks
        content = message["content"]
        st.markdown(content)

# Input for new messages
prompt = st.chat_input("Ask something...")
if prompt:
    full_response = ""
    agent_config = AgentConfig(
        model=selected_model,
        instructions=st.session_state.system_instruction,
        sampling_params={
            "strategy": {"type": "top_p", "temperature": temperature, "top_p": top_p},
        },
        toolgroups=all_toolgroups,  # Use all toolgroups automatically
        tool_choice="auto",
        input_shields=[],
        output_shields=[],
        enable_session_persistence=True,
    )
    
    try:
        agent = Agent(client, agent_config)
        session_id = agent.create_session("chat-session")
        
        # Add user input to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get response from LlamaStack API
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            # Add query context if provided
            user_message = prompt
            if query_context:
                user_message += f"\n\nContext: {query_context}"
            
            response = agent.create_turn(
                messages=[{"role": "user", "content": user_message}],
                session_id=session_id,
            )
         
            for chunk in response:
                if hasattr(chunk, 'event') and hasattr(chunk.event, 'payload'):
                    payload = chunk.event.payload
                    if hasattr(payload, 'event_type') and payload.event_type == "step_progress":
                        if hasattr(payload, 'delta') and hasattr(payload.delta, 'type') and payload.delta.type == "text":
                            full_response += payload.delta.text
                            message_placeholder.markdown(full_response + "▌")
            
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            
        # Set flag to indicate chat has been updated
        st.session_state.chat_updated = True
        
        # Force a rerun to update the UI state (including button states)
        st.rerun()
    
    except Exception as e:
        st.error(f"Error: {str(e)}")

# Reset the chat_updated flag after processing
if st.session_state.chat_updated:
    st.session_state.chat_updated = False
