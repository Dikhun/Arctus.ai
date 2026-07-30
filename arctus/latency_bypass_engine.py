import asyncio
import logging
import time
import os
from typing import Dict, Any, Optional, Tuple
import libcst as cst
import chromadb

# -------------------------------
# Telemetry & Logging Configuration
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LatencyEngine")

# -------------------------------
# Tier 0 Engine: AST Fast-Path (< 5ms)
# -------------------------------

class ASTFastPathEngine:
    """Zero-latency deterministic code modifications using LibCST."""
    
    @staticmethod
    def rename_variable(code: str, old_name: str, new_name: str) -> str:
        class VariableRenamer(cst.CSTTransformer):
            def leave_Name(self, original_node, updated_node):
                if original_node.value == old_name:
                    return updated_node.with_changes(value=new_name)
                return updated_node

        tree = cst.parse_module(code)
        return tree.visit(VariableRenamer()).code

# -------------------------------
# Tier 1 Engine: Semantic Memory Cache (< 50ms)
# -------------------------------

class LocalCacheEngine:
    """Persistent local vector cache to intercept repeated tasks."""
    
    def __init__(self, db_path: str = "./latency_cache"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.skills_collection = self.client.get_or_create_collection("skills")

    def get_cached_resolution(self, query: str, distance_threshold: float = 0.15) -> Optional[str]:
        """Search local cache; return hit only if semantic distance is under threshold."""
        try:
            results = self.skills_collection.query(query_texts=[query], n_results=1)
            if results['documents'] and results['documents'][0]:
                distance = results['distances'][0][0] if 'distances' in results and results['distances'] else 0.0
                if distance <= distance_threshold:
                    return results['documents'][0][0]
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
        return None

    def store_resolution(self, task_id: str, query: str, resolution: str):
        """Asynchronously store successful LLM resolutions for future Tier 1 hits."""
        self.skills_collection.add(
            ids=[task_id],
            documents=[resolution],
            metadatas=[{"query": query}]
        )

# -------------------------------
# Git Context Shrinker (Latency Reduction for Prompts)
# -------------------------------

class GitDiffGuardrails:
    """Shrinks prompt payload size to reduce token count and LLM time-to-first-byte (TTFB)."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    async def get_minimal_diff_context(self, file_path: str) -> str:
        """Fetch git diff asynchronously without blocking the event loop."""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, "diff", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        
        # Stripping out deleted lines to trim token payload size
        lines = stdout.decode().splitlines()
        minimal_lines = [line for line in lines if not line.startswith("-")]
        return "\n".join(minimal_lines)

# -------------------------------
# Core Fast-Path Router
# -------------------------------

class LatencyOptimizedRouter:
    """Routes incoming execution requests to the lowest-latency tier possible."""
    
    def __init__(self, cache_engine: LocalCacheEngine, ast_engine: ASTFastPathEngine):
        self.cache = cache_engine
        self.ast = ast_engine

    async def execute(self, task: str, code_context: str, params: Dict[str, str] = None) -> Tuple[str, str, float]:
        """
        Executes task and returns: (Result, Execution_Tier, Latency_ms)
        """
        start_time = time.perf_counter()
        params = params or {}

        # --- TIER 0: AST Fast-Path (< 5ms) ---
        if task == "rename_variable" and "old_name" in params and "new_name" in params:
            try:
                result = self.ast.rename_variable(code_context, params["old_name"], params["new_name"])
                latency = (time.perf_counter() - start_time) * 1000
                logger.info(f"Tier 0 HIT (AST) -> Completed in {latency:.2f} ms")
                return result, "Tier 0 (AST)", latency
            except Exception as e:
                logger.warning(f"Tier 0 bypass failed: {e}. Slipping to Tier 1.")

        # --- TIER 1: Local Cache Hit (< 50ms) ---
        cached_solution = self.cache.get_cached_resolution(task)
        if cached_solution:
            latency = (time.perf_counter() - start_time) * 1000
            logger.info(f"Tier 1 HIT (Local Cache) -> Completed in {latency:.2f} ms")
            return cached_solution, "Tier 1 (Cache)", latency

        # --- TIER 2: High-Latency LLM Fallback (> 1000ms) ---
        logger.warning("Fast-paths missed. Triggering Tier 2 LLM Fallback...")
        result = await self._invoke_llm_fallback(task, code_context)
        latency = (time.perf_counter() - start_time) * 1000
        
        # Store result to populate Tier 1 for future runs
        self.cache.store_resolution(f"task_{int(time.time())}", task, result)
        
        return result, "Tier 2 (LLM Fallback)", latency

    async def _invoke_llm_fallback(self, task: str, context: str) -> str:
        """Simulate high-latency network request to an LLM provider."""
        await asyncio.sleep(0.8) # Simulate 800ms network latency
        return f"# LLM Resolved Output for {task}\n{context}"

# -------------------------------
# Execution Benchmark Entry
# -------------------------------

async def main():
    cache_engine = LocalCacheEngine()
    ast_engine = ASTFastPathEngine()
    router = LatencyOptimizedRouter(cache_engine, ast_engine)

    code_sample = """
def process_data():
    raw_value = 100
    return raw_value
    """

    print("\n--- Benchmark Run 1: Deterministic Task (Expect Tier 0 AST) ---")
    _, tier, latency = await router.execute(
        task="rename_variable", 
        code_context=code_sample, 
        params={"old_name": "raw_value", "new_name": "clean_value"}
    )
    print(f"Tier: {tier} | Latency: {latency:.2f} ms")

    print("\n--- Benchmark Run 2: Non-Deterministic Task (Expect Tier 2 LLM) ---")
    _, tier, latency = await router.execute(
        task="refactor_optimizations", 
        code_context=code_sample
    )
    print(f"Tier: {tier} | Latency: {latency:.2f} ms")

if __name__ == "__main__":
    asyncio.run(main())
              
