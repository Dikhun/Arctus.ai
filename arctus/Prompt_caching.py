pip install pydantic python-telegram-bot chromadb
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import hashlib
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from chromadb.config import Settings
from chromadb import Client

# ----------------------------
# AST TEMPLATE DEFINITION
# ----------------------------
class CapabilityBlock(BaseModel):
    name: str
    description: str
    params: Optional[Dict[str, str]] = None

class PromptAST(BaseModel):
    system_template: str
    role_definition: str
    capability_blocks: List[CapabilityBlock]
    tool_definitions: List[str]
    memory_references: Optional[List[str]] = None
    dynamic_user_task: str

    def compile_prompt(self) -> str:
        """
        Compile the prompt by combining static and dynamic components.
        """
        prompt = (
            f"{self.system_template}\n\n"
            f"Role: {self.role_definition}\n\n"
            f"Capabilities:\n"
        )

        for block in self.capability_blocks:
            prompt += f"- {block.name}: {block.description}\n"

        if self.tool_definitions:
            prompt += f"\nTools Available: {', '.join(self.tool_definitions)}\n"

        if self.memory_references:
            prompt += f"\nMemory: {', '.join(self.memory_references)}\n"

        prompt += f"\nUser Task: {self.dynamic_user_task}\n"
        return prompt

# ----------------------------
# PROMPT CACHING
# ----------------------------
PROMPT_CACHE = {}

def compute_hash(data: Any) -> str:
    """
    Compute a unique hash for the given data (e.g., for AST templates).
    """
    data_bytes = str(data).encode('utf-8')
    return hashlib.sha256(data_bytes).hexdigest()

def cache_prompt(ast_prompt: PromptAST) -> str:
    """
    Cache a compiled prompt and return its hash.
    """
    compiled = ast_prompt.compile_prompt()
    prompt_hash = compute_hash(compiled)
    PROMPT_CACHE[prompt_hash] = compiled
    return prompt_hash

def get_cached_prompt(prompt_hash: str) -> Optional[str]:
    """
    Retrieve a cached prompt by its hash.
    """
    return PROMPT_CACHE.get(prompt_hash, None)

# ----------------------------
# SEMANTIC CONTEXT RETRIEVAL
# ----------------------------
def init_chromadb():
    client = Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory="./chromadb"))
    return client

def add_documents_to_chromadb(client, collection_name: str, documents: List[Dict]):
    collection = client.get_or_create_collection(name=collection_name)
    for doc in documents:
        collection.add(
            documents=[doc['content']],
            metadatas=[doc['metadata']],
            ids=[doc['id']]
        )

def query_with_chromadb(client, collection_name: str, user_query: str, top_k: int = 3) -> List[str]:
    collection = client.get_collection(name=collection_name)
    results = collection.query(query_texts=[user_query], n_results=top_k)
    return results['documents'][0]  # Return top-k relevant responses

def query_with_ripgrep(search_term: str, directory: str) -> List[str]:
    try:
        output = subprocess.check_output(["rg", search_term, directory], universal_newlines=True)
        return output.strip().split("\n")
    except subprocess.CalledProcessError:
        return []  # No results found

# ----------------------------
# TELEGRAM GATEWAY
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session_id = f"session-{user_id}"
    context.user_data['session_id'] = session_id

    # Example: Create example AST prompt for user based on request
    capabilities = [
        CapabilityBlock(name="Code Generator", description="Generate code based on user input."),
        CapabilityBlock(name="Bug Fixer", description="Identify and fix bugs in given code.")
    ]

    user_request = "Write a Python function to process a CSV file."

    ast_prompt = PromptAST(
        system_template="You are a well-trained AI focused on assisting developers.",
        role_definition="Your task is to help with coding-related queries and solutions.",
        capability_blocks=capabilities,
        tool_definitions=["Python", "Git"],
        memory_references=None,
        dynamic_user_task=user_request
    )

    # Check for cached prompt
    prompt_hash = compute_hash(ast_prompt)
    cached_response = get_cached_prompt(prompt_hash)

    if cached_response:
        await update.message.reply_text(f"Cached Prompt:\n{cached_response}")
    else:
        # Compile prompt, cache it, and send response
        compiled_prompt = ast_prompt.compile_prompt()
        cache_prompt(ast_prompt)
        await update.message.reply_text(f"New Prompt Compiled:\n{compiled_prompt}")

# Main application
application = ApplicationBuilder().token("YOUR-TELEGRAM-TOKEN").build()
application.add_handler(CommandHandler("start", start))
application.run_polling()
