import asyncio
import os
import sys
from dotenv import load_dotenv

# Enterprise Framework: AutoGen (v0.4+ AgentChat API)
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

async def run_autonomous_project_manager() -> None:
    """
    Initializes and orchestrates a multi-agent team to autonomously break down 
    a project requirement into a strictly formatted Work Breakdown Structure (WBS).
    """
    
    # 1. Environment & Security Validation
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("CRITICAL ERROR: OPENAI_API_KEY environment variable is missing.")
        sys.exit(1)

    # 2. Model Client Initialization (using gpt-4o for production reliability)
    # Temperature is kept low (0.2) to reduce hallucinations and ensure deterministic output.
    try:
        model_client = OpenAIChatCompletionClient(
            model="gpt-4o",
            api_key=api_key,
            temperature=0.2 
        )
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to initialize Model Client. {e}")
        sys.exit(1)

    # 3. Agent Capability Definitions
    scope_analyzer = AssistantAgent(
        name="Scope_Analyzer",
        model_client=model_client,
        description="Analyzes the initial project scope, identifies technical dependencies, and defines success criteria.",
        system_message=(
            "You are a strict, enterprise-grade Requirements Analyst. "
            "Break down the user's initial project request into 3 core technical deliverables. "
            "Be extremely concise. Do not write code."
        )
    )

    task_decomposer = AssistantAgent(
        name="Task_Decomposer",
        model_client=model_client,
        description="Consumes scope deliverables and creates a Work Breakdown Structure (WBS).",
        system_message=(
            "You are a Lead Execution Engineer. You receive deliverables from the Scope_Analyzer. "
            "Convert them into a bulleted Work Breakdown Structure (WBS) with clear execution steps. "
            "When the WBS is fully complete and ready for execution, you must end your response "
            "with the exact word: 'TERMINATE_PLANNING'."
        )
    )

    # 4. Strict Termination Constraints (Risk Management)
    # Prevents infinite loops by stopping when the task is done OR if the message limit is breached.
    text_termination = TextMentionTermination("TERMINATE_PLANNING")
    max_messages = MaxMessageTermination(max_messages=6)
    safety_termination_condition = text_termination | max_messages

    # 5. Team Orchestration Initialization
    planning_team = RoundRobinGroupChat(
        participants=[scope_analyzer, task_decomposer],
        termination_condition=safety_termination_condition
    )

    # 6. Execution and Progress Monitoring
    project_intake_prompt = (
        "Design a secure, cloud-native REST API for a real-time financial transaction ledger. "
        "It must support high throughput and maintain ACID compliance."
    )
    
    print("--- [APM STATUS] Initializing Project Planning Sequence ---\n")
    
    try:
        # Utilizing run_stream for real-time memory-efficient processing
        execution_stream = planning_team.run_stream(task=project_intake_prompt)
        
        async for message in execution_stream:
            # Differentiate between standard chat messages and system/task result messages
            if hasattr(message, "source") and hasattr(message, "content"):
                print(f"[{message.source.upper()}]:\n{message.content}\n")
                print("-" * 60)
                
    except Exception as e:
        print(f"\n[EXECUTION HALTED] Orchestration failed due to unhandled exception: {e}")
        sys.exit(1)
        
    print("\n--- [APM STATUS] Project Planning Sequence Terminated Successfully ---")

if __name__ == "__main__":
    # Ensure graceful handling of asynchronous execution loops during autonomous deployment
    try:
        asyncio.run(run_autonomous_project_manager())
    except KeyboardInterrupt:
        print("\n[APM STATUS] Execution manually overridden and safely aborted.")
        sys.exit(0)
      
