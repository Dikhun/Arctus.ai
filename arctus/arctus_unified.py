"""
Arctus: Autonomous Skill Development Framework
----------------------------------------------
A closed-loop orchestration framework that observes, generates, 
validates, registers, and dynamically executes autonomous skills.
"""

import os
import json
import sqlite3
import ast
import traceback
import importlib.util
import logging.config
from typing import Dict, Any, Optional, List
from pathlib import Path

# Graceful degradation for vision dependencies
try:
    import cv2
    import pytesseract
    HAS_VISION_DEPS = True
except ImportError:
    HAS_VISION_DEPS = False

# ==========================================
# 1. LOGGING CONFIGURATION
# ==========================================
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("ArctusCore")


# ==========================================
# 2. VISION COMPONENT
# ==========================================
class Vision:
    """Handles visual input processing such as OCR and UI element detection."""

    def analyze_screenshot(self, image_path: str) -> Dict[str, Any]:
        """Perform OCR and UI element detection on a screenshot."""
        if not HAS_VISION_DEPS:
            logger.warning("Vision dependencies (cv2, pytesseract) missing. Mocking OCR.")
            return {"text": "mock_extracted_text", "ui_elements": []}

        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Image not found at {image_path}")
            
        text = pytesseract.image_to_string(image)
        return {
            "text": text.strip(),
            "ui_elements": []  # Placeholder for bounding box integrations (e.g., YOLO)
        }

    def extract_frame_from_video(self, video_path: str, output_dir: str):
        """Extract frames from a video for temporal workflow learning."""
        if not HAS_VISION_DEPS:
            logger.warning("Vision dependencies missing. Skipping extraction.")
            return

        os.makedirs(output_dir, exist_ok=True)
        video = cv2.VideoCapture(video_path)
        frame_count = 0

        while True:
            success, frame = video.read()
            if not success:
                break
            cv2.imwrite(f"{output_dir}/frame_{frame_count}.jpg", frame)
            frame_count += 1

        video.release()
        logger.info(f"Extracted {frame_count} frames to {output_dir}")


# ==========================================
# 3. REGISTRY (PERSISTENCE)
# ==========================================
class SkillRegistry:
    """Registry for managing and versioning reusable dynamic skills."""

    def __init__(self, db_path: str = "skills_registry.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._initialize_db()

    def _initialize_db(self):
        """Create necessary tables. FIXED: UNIQUE constraint on (name, version)."""
        query = """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            manifest TEXT NOT NULL,
            skill_path TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            UNIQUE(name, version)
        );
        """
        self.conn.execute(query)
        self.conn.commit()

    def register_skill(self, name: str, version: str, manifest: str, skill_path: str) -> bool:
        """Add a new versioned skill into the SQLite registry."""
        try:
            query = """
            INSERT INTO skills (name, version, manifest, skill_path) 
            VALUES (?, ?, ?, ?)
            """
            self.conn.execute(query, (name, version, manifest, skill_path))
            self.conn.commit()
            logger.info(f"Successfully registered skill: {name} (v{version})")
            return True
        except sqlite3.IntegrityError:
            logger.error(f"Skill {name} v{version} already exists in registry.")
            return False

    def get_skill(self, name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve a specific or the latest skill from the registry."""
        if version:
            query = "SELECT id, name, version, manifest, skill_path FROM skills WHERE name=? AND version=? AND is_active=1"
            params = (name, version)
        else:
            # Fetch latest version if none specified
            query = "SELECT id, name, version, manifest, skill_path FROM skills WHERE name=? AND is_active=1 ORDER BY id DESC LIMIT 1"
            params = (name,)

        cursor = self.conn.execute(query, params)
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "version": row[2],
                "manifest": json.loads(row[3]),
                "skill_path": row[4]
            }
        return None


# ==========================================
# 4. SKILL GENERATOR (SYNTHESIS & SANDBOX)
# ==========================================
class SkillGenerator:
    """Validates, generates, and registers dynamically created skills."""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.base_dir = Path("arctus/skills")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _validate_syntax(self, code: str) -> bool:
        """Sandbox Step 1: Ensure generated code is syntactically valid."""
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            logger.error(f"Syntax validation failed for generated code: {e}")
            return False

    def generate_and_register(self, task_name: str, version: str, logic_code: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Writes valid task logic to disk and automatically registers it."""
        
        # 1. Sandbox Validation
        if not self._validate_syntax(logic_code):
            return {"status": "error", "reason": "Syntax validation failed"}

        # 2. Setup Isolation Directory
        skill_dir = self.base_dir / f"{task_name}_v{version.replace('.', '_')}"
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_file = skill_dir / "skill.py"
        manifest_file = skill_dir / "manifest.json"

        # 3. Write Artifacts (Replaced yaml with json for stdlib support)
        try:
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(logic_code)

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to write skill artifacts to disk: {e}")
            return {"status": "error", "reason": "IO Error"}

        # 4. Auto-Register to Database
        success = self.registry.register_skill(
            name=task_name,
            version=version,
            manifest=json.dumps(metadata),
            skill_path=str(skill_dir)
        )

        if success:
            return {"status": "success", "skill_path": str(skill_dir)}
        return {"status": "error", "reason": "Registry insertion failed"}


# ==========================================
# 5. EXECUTION ENGINE (DYNAMIC LOADER)
# ==========================================
class ExecutionEngine:
    """Handles standard workflows and dynamic execution of learned skills."""
    
    def plan_workflow(self, request: str) -> str:
        """Stub for workflow decomposition."""
        logger.info("Planning complex workflow...")
        return "plan_data_extraction"

    def execute(self, plan: str) -> str:
        return f"Execution of {plan} complete."

    def load_and_run_skill(self, skill_path: str, func_name: str = "execute", **kwargs) -> Any:
        """Dynamically imports a generated Python file and runs its entrypoint."""
        module_path = Path(skill_path) / "skill.py"
        if not module_path.exists():
            raise FileNotFoundError(f"Skill module missing at {module_path}")

        # Dynamic Module Loading via importlib
        module_name = f"dynamic_skill_{os.path.basename(skill_path)}"
        spec = importlib.util.spec_from_file_location(module_name, str(module_path))
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
            # Fetch the target function (default 'execute')
            target_func = getattr(module, func_name)
            return target_func(**kwargs)
        except Exception as e:
            logger.error(f"Dynamic skill execution failed:\n{traceback.format_exc()}")
            return None


class AgentRegistry:
    """Mock for retrieving specialized base agents."""
    def get_agent(self, name: str):
        class MockAgent:
            def execute_task(self, req: str):
                return f"[{name} Agent] Handled request: {req}"
        return MockAgent()


# ==========================================
# 6. ORCHESTRATION (QUEEN AGENT)
# ==========================================
class Queen:
    """The Queen agent serves as the central orchestrator of the system."""

    def __init__(self, agent_registry: AgentRegistry, skill_registry: SkillRegistry, execution_engine: ExecutionEngine):
        self.agent_registry = agent_registry
        self.skill_registry = skill_registry
        self.execution_engine = execution_engine

    def process_request(self, user_request: str) -> Any:
        """
        Main handler. Now checks if a learned skill already exists 
        before planning a complex multi-agent workflow.
        """
        logger.info(f"Queen received request: '{user_request}'")

        # Step 1: Check if an Autonomous Skill was already learned for this
        task_intent = self._extract_intent(user_request)
        known_skill = self.skill_registry.get_skill(task_intent)
        
        if known_skill:
            logger.info(f"Using autonomously learned skill: {task_intent} v{known_skill['version']}")
            return self.execution_engine.load_and_run_skill(known_skill['skill_path'])

        # Step 2: Fallback to standard complexity analysis
        task_complexity = self._analyze_complexity(user_request)

        if task_complexity == 'simple':
            return self._respond_directly(user_request)
        elif task_complexity == 'medium':
            return self._execute_single_agent(user_request)
        else:
            return self._execute_complex_workflow(user_request)

    def _extract_intent(self, request: str) -> str:
        """Simple intent parser mock. In reality, handled by LLM."""
        if "extract data" in request.lower():
            return "data_extraction"
        return "unknown_task"

    def _analyze_complexity(self, request: str) -> str:
        if len(request) < 30:
            return 'simple'
        elif len(request) < 100:
            return 'medium'
        return 'complex'

    def _respond_directly(self, request: str) -> str:
        return f"Simple response to: {request}"

    def _execute_single_agent(self, request: str) -> Any:
        agent = self.agent_registry.get_agent('Developer')
        return agent.execute_task(request)

    def _execute_complex_workflow(self, request: str) -> Any:
        plan = self.execution_engine.plan_workflow(request)
        return self.execution_engine.execute(plan)


# ==========================================
# 7. END-TO-END SYSTEM TEST
# ==========================================
if __name__ == "__main__":
    logger.info("Initializing Arctus Framework...")

    # 1. Initialize Subsystems
    skill_registry = SkillRegistry()
    agent_registry = AgentRegistry()
    execution_engine = ExecutionEngine()
    skill_generator = SkillGenerator(skill_registry)
    queen = Queen(agent_registry, skill_registry, execution_engine)

    # 2. Simulate the 'Autonomous Skill Development' Phase
    logger.info("--- PHASE 1: Autonomous Learning Phase ---")
    
    # Imagine the Vision component and LLM deduced this Python logic:
    learned_logic = '''
def execute(**kwargs):
    return "SUCCESS: I dynamically extracted the data exactly as taught!"
'''
    learned_meta = {
        "description": "Extracts tabular data from generic invoices.",
        "dependencies": ["pandas"]
    }
    
    # Framework generates and automatically registers the skill
    gen_result = skill_generator.generate_and_register(
        task_name="data_extraction", 
        version="1.0.0", 
        logic_code=learned_logic, 
        metadata=learned_meta
    )

    # 3. Test the Closed Loop via Queen Orchestrator
    logger.info("\n--- PHASE 2: Execution Phase ---")
    
    # A request that matches our newly learned skill
    response = queen.process_request("Please extract data from the recent invoices.")
    logger.info(f"Final Output: {response}")
          
