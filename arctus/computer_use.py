"""Computer-use: display server + browser automation + screenshot-reason-act loop.

Provides agents with the ability to interact with a local display (mouse,
keyboard, screenshots) and a headless browser (Playwright/Chromium). Used
by the orchestrator when a step has tier="computer-use".

All third-party imports (pyautogui, playwright, PIL) are LAZY — inside
functions — so the package stays zero-dependency when computer-use is not
invoked.

Safety:
  - pyautogui.FAILSAFE = True (mouse to corner = abort).
  - All operations are bounded by max_steps in the execution loop.
  - Screenshot-reason-act pattern: the LLM reasons over a screenshot
    BEFORE taking action, preventing blind/guessing clicks.

Set-of-Marks (SoM): annotates screenshots with numbered bounding boxes
to solve the "where to click" problem for vision models.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional

logger = logging.getLogger("arctus.computer_use")


# ── Display & Input tools ─────────────────────────────────────────────

def take_screenshot() -> str:
    """Captures the current sandbox display and returns a Base64 PNG string.

    Requires: pyautogui, Pillow (PIL). Lazy import.
    Raises ImportError with a clear message if deps are missing.
    """
    import pyautogui
    from PIL import Image  # type: ignore

    pyautogui.FAILSAFE = True
    screenshot: Image.Image = pyautogui.screenshot()
    buffered = BytesIO()
    screenshot.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def execute_mouse_click(x: int, y: int, button: str = "left") -> str:
    """Moves to (x, y) coordinates and performs a mouse click."""
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.moveTo(x, y, duration=0.2)
    pyautogui.click(button=button)
    return f"Clicked {button} at ({x}, {y})"


def execute_keyboard_type(text: str, press_enter: bool = True) -> str:
    """Simulates typing text on the keyboard."""
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.write(text, interval=0.03)
    if press_enter:
        pyautogui.press("enter")
    return f"Typed: '{text}'"


def execute_key_combination(keys: list) -> str:
    """Triggers hotkeys like ['ctrl', 'c'] or ['alt', 'tab']."""
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.hotkey(*keys)
    return f"Pressed key combination: {keys}"


# ── Browser automation (Playwright) ──────────────────────────────────

_browser_page = None


def _get_browser_page():
    """Lazy-initialize a Playwright Chromium page (singleton)."""
    global _browser_page
    if _browser_page is None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            _browser_page = browser.new_page()
            logger.info("Playwright Chromium launched (headless)")
        except ImportError:
            raise ImportError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
    return _browser_page


def browser_navigate(url: str) -> str:
    """Navigate to a URL in the headless browser. Returns page title."""
    page = _get_browser_page()
    page.goto(url, timeout=30000)
    return f"Navigated to {url} — title: {page.title()}"


def browser_screenshot() -> str:
    """Take a screenshot of the current browser page. Returns Base64 PNG."""
    page = _get_browser_page()
    png_bytes = page.screenshot()
    return base64.b64encode(png_bytes).decode("utf-8")


def browser_close() -> str:
    """Close the browser instance."""
    global _browser_page
    if _browser_page is not None:
        _browser_page.close()
        _browser_page = None
    return "Browser closed"


# ── Set-of-Marks (SoM) helper ────────────────────────────────────────

@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int
    label: str = ""


def annotate_with_som(bounding_boxes: List[BoundingBox]) -> str:
    """Annotate a screenshot with numbered bounding boxes (Set-of-Marks).

    The vision model can then reference "click on box 3" instead of raw
    pixel coordinates. Returns a text summary of the marks for the LLM
    context.

    Note: actual image annotation requires Pillow draw; this returns
    the text map. For full visual annotation, use the SoMImageHelper.
    """
    lines = ["Set-of-Marks bounding boxes:"]
    for i, bb in enumerate(bounding_boxes, 1):
        label = f" ({bb.label})" if bb.label else ""
        lines.append(
            f"  Box {i}: x={bb.x} y={bb.y} w={bb.width} h={bb.height}{label} "
            f"-> center=({bb.x + bb.width // 2}, {bb.y + bb.height // 2})"
        )
    return "\n".join(lines)


# ── Screenshot-Reason-Act Loop ────────────────────────────────────────

class ToolCall:
    """Parsed tool call from the LLM response."""

    def __init__(self, name: str, args: Dict[str, Any]):
        self.name = name
        self.args = args


class MockLLMClient:
    """Placeholder LLM client interface.

    Replace with the actual LLM client that parses tool-call responses.
    Must implement: get_action(messages) -> ToolCall
    """

    def get_action(self, messages: list) -> ToolCall:
        raise NotImplementedError("Wire a real LLM client here.")


def agent_execution_loop(
    user_goal: str,
    llm_client: Any,
    max_steps: int = 15,
    use_display: bool = True,
    use_browser: bool = False,
) -> Dict[str, Any]:
    """The agentic screenshot-reason-act loop.

    1. Capture state (screenshot / DOM state).
    2. Feed to LLM with tool declarations.
    3. Execute returned tool call (mouse/keyboard/browser).
    4. Repeat until task completed or max_steps reached.

    Args:
        user_goal: What the user wants the agent to do.
        llm_client: An object with get_action(messages) -> ToolCall.
        max_steps: Maximum number of action steps.
        use_display: Use pyautogui screenshot (requires display server).
        use_browser: Use Playwright browser screenshots instead.

    Returns:
        Dict with 'goal_achieved', 'steps_taken', 'summary', 'steps'.
    """
    tool_declarations = (
        "Available tools:\n"
        "  mouse_click(x, y, button='left')\n"
        "  type_text(text, press_enter=True)\n"
        "  key_combination(keys: list)\n"
        "  navigate_url(url)\n"
        "  task_complete(summary: str)\n"
    )

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a local OS/Browser agent. Use available mouse, keyboard, "
                "and web tools to fulfill the user request. "
                "When you believe the task is complete, call task_complete(summary). "
                "Be precise with coordinates.\n\n" + tool_declarations
            ),
        },
        {"role": "user", "content": user_goal},
    ]

    steps_taken = 0
    step_log: List[Dict[str, Any]] = []

    for step in range(max_steps):
        # Step A: Capture current state
        try:
            if use_browser:
                screen_b64 = browser_screenshot()
            elif use_display:
                screen_b64 = take_screenshot()
            else:
                screen_b64 = ""
        except Exception as e:
            logger.warning("Screenshot failed at step %d: %s", step + 1, e)
            screen_b64 = ""

        # Step B: Attach visual context
        content: List[Any] = [
            {"type": "text", "text": f"Current step: {step + 1}. What is your next action?"}
        ]
        if screen_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": screen_b64},
            })

        messages.append({"role": "user", "content": content})

        # Step C: Ask LLM for the next tool call
        try:
            tool_call = llm_client.get_action(messages)
        except Exception as e:
            logger.error("LLM call failed at step %d: %s", step + 1, e)
            step_log.append({"step": step + 1, "error": str(e)})
            break

        if tool_call.name == "task_complete":
            logger.info("Goal Achieved: %s", tool_call.args.get("summary", ""))
            messages.append({"role": "environment", "content": f"Goal achieved: {tool_call.args.get('summary', '')}"})
            step_log.append({"step": step + 1, "action": "task_complete", "args": tool_call.args})
            steps_taken = step + 1
            break

        # Step D: Dispatch to local execution functions
        result = ""
        try:
            if tool_call.name == "mouse_click":
                result = execute_mouse_click(
                    int(tool_call.args.get("x", 0)),
                    int(tool_call.args.get("y", 0)),
                    str(tool_call.args.get("button", "left")),
                )
            elif tool_call.name == "type_text":
                result = execute_keyboard_type(
                    str(tool_call.args.get("text", "")),
                    bool(tool_call.args.get("press_enter", True)),
                )
            elif tool_call.name == "key_combination":
                result = execute_key_combination(list(tool_call.args.get("keys", [])))
            elif tool_call.name == "navigate_url":
                result = browser_navigate(str(tool_call.args.get("url", "")))
            else:
                result = f"Unknown tool: {tool_call.name}"
                logger.warning("Unknown tool call: %s", tool_call.name)
        except Exception as e:
            result = f"Error: {e}"
            logger.error("Tool execution error at step %d: %s", step + 1, e)

        # Step E: Append result back to context history
        messages.append({"role": "environment", "content": result})
        step_log.append({"step": step + 1, "action": tool_call.name, "args": tool_call.args, "result": result})

    return {
        "goal_achieved": any(s.get("action") == "task_complete" for s in step_log),
        "steps_taken": steps_taken or len(step_log),
        "summary": step_log[-1].get("args", {}).get("summary", "") if step_log else "",
        "steps": step_log,
    }
