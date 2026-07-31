import json
from typing import List, Dict, Any, Callable

class AgentVM:
    """
    A lightweight Virtual Machine architecture for orchestrating AI Agents.
    Executes a list of instructions (bytecodes) to manage agent state and workflows.
    """
    
    def __init__(self, program: List[Dict[str, Any]], llm_caller: Callable[[str, str, str], str]):
        self.program = program          # The workflow instruction set
        self.pc = 0                     # Program Counter (current step)
        self.agents = {}                # Registry of spawned agents & their system prompts
        self.memory = {}                # Shared state / Context memory
        self.running = True
        self.llm_caller = llm_caller    # Pluggable function to call actual LLMs
        self.log = []

    def log_event(self, msg: str):
        print(f"[VM-PC:{self.pc:02d}] {msg}")
        self.log.append(msg)

    def step(self):
        """Executes a single instruction and advances the Program Counter."""
        if self.pc >= len(self.program):
            self.running = False
            return

        instruction = self.program[self.pc]
        op = instruction.get("op")

        if op == "SPAWN":
            # Initialize a new agent persona
            name = instruction["name"]
            self.agents[name] = instruction.get("system_prompt", "You are a helpful assistant.")
            self.log_event(f"Spawned Agent: '{name}'")

        elif op == "PROMPT":
            # Send context to an agent and store the response
            agent_name = instruction["agent"]
            prompt = instruction.get("prompt", "")
            
            # Resolve memory variables (e.g., "$draft" -> actual memory value)
            if prompt.startswith("$"):
                prompt = self.memory.get(prompt[1:], "")

            sys_prompt = self.agents.get(agent_name, "")
            response = self.llm_caller(agent_name, sys_prompt, prompt)
            
            store_key = instruction.get("store_as")
            if store_key:
                self.memory[store_key] = response
                self.log_event(f"Prompted '{agent_name}'. Saved output to memory key: '${store_key}'")

        elif op == "JUMP_IF_CONTAINS":
            # Conditional branching for workflows (e.g., if a reviewer says "REJECT")
            key = instruction["memory_key"]
            val = instruction["substring"].lower()
            target_pc = instruction["target_pc"]
            
            if val in self.memory.get(key, "").lower():
                self.log_event(f"Condition met ('{val}' in '${key}'). Branching to PC {target_pc}")
                self.pc = target_pc
                return  # Skip default PC increment

        elif op == "PRINT_MEMORY":
            self.log_event(f"CURRENT SHARED MEMORY:\n{json.dumps(self.memory, indent=2)}")

        elif op == "HALT":
            self.log_event("HALT instruction reached. Shutting down VM.")
            self.running = False
            return

        else:
            self.log_event(f"ERROR: Unknown OpCode: {op}")
            self.running = False
            return

        self.pc += 1

    def run(self):
        """Runs the VM loop until completion or HALT."""
        self.log_event("Booting Agent VM...")
        while self.running:
            self.step()
        self.log_event("Execution Finished.")


# ==========================================
# EXAMPLE USAGE & MOCK LLM
# ==========================================
if __name__ == "__main__":
    
    # 1. Define a mock LLM (Replace this with real OpenAI/Anthropic API calls)
    def mock_llm_provider(agent: str, sys_prompt: str, user_prompt: str) -> str:
        if agent == "Reviewer" and "V1" in user_prompt:
            return "This draft is a bit thin. REJECT."
        if agent == "Reviewer":
            return "Looks great! APPROVE."
        if agent == "Writer" and "thin" in user_prompt: # Rewriting based on feedback
            return "Here is a much better draft about AI (V2)."
        return "Here is a draft about AI (V1)."

    # 2. Define the multi-agent workflow program
    workflow = [
        # 0: Setup Agents
        {"op": "SPAWN", "name": "Writer", "system_prompt": "You are a tech copywriter."},
        {"op": "SPAWN", "name": "Reviewer", "system_prompt": "You approve or reject drafts."},
        
        # 2: Drafting Loop
        {"op": "PROMPT", "agent": "Writer", "prompt": "Write a 2-sentence intro to AI.", "store_as": "draft"},
        {"op": "PROMPT", "agent": "Reviewer", "prompt": "$draft", "store_as": "feedback"},
        
        # 4: Conditional Routing
        {"op": "JUMP_IF_CONTAINS", "memory_key": "feedback", "substring": "REJECT", "target_pc": 6},
        {"op": "HALT"}, # Ends if approved
        
        # 6: Rewrite Routine (Triggered by Jump)
        {"op": "PROMPT", "agent": "Writer", "prompt": "Rewrite this. Feedback: $feedback", "store_as": "draft"},
        {"op": "PROMPT", "agent": "Reviewer", "prompt": "$draft", "store_as": "feedback"},
        {"op": "PRINT_MEMORY"},
        {"op": "HALT"}
    ]

    # 3. Boot the VM and execute the program
    vm = AgentVM(program=workflow, llm_caller=mock_llm_provider)
    vm.run()
  
