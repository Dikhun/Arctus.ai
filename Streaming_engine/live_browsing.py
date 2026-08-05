#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Live Browser Streaming Engine
=================================================================
Real-time browser automation streaming with Playwright integration,
screenshot streaming, DOM synchronization, and session recording.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# Playwright integration
try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# WebSocket support
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger("arctus.browser")
logger.setLevel(logging.DEBUG)

# ============================================================================
# DATA MODELS
# ============================================================================

class BrowserEventType(Enum):
    SCREENSHOT = auto()
    DOM_UPDATE = auto()
    MOUSE_MOVE = auto()
    CLICK = auto()
    KEYBOARD = auto()
    NAVIGATION = auto()
    CONSOLE = auto()
    DOWNLOAD = auto()
    UPLOAD = auto()
    COOKIE_CHANGE = auto()
    TAB_CHANGE = auto()
    VIEWPORT_CHANGE = auto()

@dataclass(slots=True)
class BrowserEvent:
    """Browser automation event for streaming."""
    event_type: BrowserEventType
    timestamp: datetime
    session_id: str
    tab_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    screenshot: Optional[bytes] = None
    
    def to_json(self) -> str:
        payload = {
            "type": self.event_type.name,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "tab_id": self.tab_id,
            "data": self.data,
        }
        if self.screenshot:
            payload["screenshot"] = base64.b64encode(self.screenshot).decode()
        return json.dumps(payload)
    
    @classmethod
    def from_json(cls, raw: str) -> BrowserEvent:
        data = json.loads(raw)
        return cls(
            event_type=BrowserEventType[data["type"]],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_id=data["session_id"],
            tab_id=data.get("tab_id"),
            data=data.get("data", {}),
            screenshot=base64.b64decode(data["screenshot"]) if data.get("screenshot") else None,
        )

@dataclass
class TabState:
    """State of a single browser tab."""
    tab_id: str
    url: str = "about:blank"
    title: str = ""
    viewport_width: int = 1280
    viewport_height: int = 720
    scroll_x: int = 0
    scroll_y: int = 0
    mouse_x: int = 0
    mouse_y: int = 0
    dom_hash: str = ""
    active: bool = True

@dataclass
class BrowserSession:
    """Active browser automation session."""
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    browser_type: str = "chromium"
    headless: bool = True
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    
    # Playwright references (not serialized)
    browser: Optional[Browser] = field(default=None, repr=False)
    context: Optional[BrowserContext] = field(default=None, repr=False)
    pages: Dict[str, Page] = field(default_factory=dict, repr=False)
    tabs: Dict[str, TabState] = field(default_factory=dict)
    
    # Streaming
    viewers: Set[WebSocketServerProtocol] = field(default_factory=set, repr=False)
    streaming: bool = False
    screenshot_interval: float = 0.5  # seconds
    
    # Recording
    recording: bool = False
    recording_path: Optional[Path] = None
    events: List[BrowserEvent] = field(default_factory=list)
    
    # State
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    downloads: List[Dict[str, Any]] = field(default_factory=list)
    uploads: List[Dict[str, Any]] = field(default_factory=list)
    active: bool = True

# ============================================================================
# DOM SYNCHRONIZATION
# ============================================================================

class DomSynchronizer:
    """Synchronize DOM state between browser and viewers."""
    
    def __init__(self):
        self._dom_cache: Dict[str, str] = {}  # tab_id -> html hash
    
    async def capture_dom(self, page: Page) -> Dict[str, Any]:
        """Capture current DOM state."""
        try:
            # Get full HTML
            html = await page.content()
            # Get visible text
            text = await page.evaluate("() => document.body.innerText")
            # Get element bounding boxes
            elements = await page.evaluate("""
                () => Array.from(document.querySelectorAll('*')).map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    class: el.className,
                    rect: el.getBoundingClientRect ? {
                        x: el.getBoundingClientRect().x,
                        y: el.getBoundingClientRect().y,
                        w: el.getBoundingClientRect().width,
                        h: el.getBoundingClientRect().height
                    } : null
                }))
            """)
            
            dom_hash = hashlib.sha256(html.encode()).hexdigest()[:16]
            
            return {
                "html_hash": dom_hash,
                "text_preview": text[:500] if text else "",
                "element_count": len(elements),
                "elements": elements[:100],  # Limit for performance
            }
        except Exception as e:
            logger.error(f"DOM capture failed: {e}")
            return {"error": str(e)}
    
    async def get_dom_diff(self, tab_id: str, current_dom: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Calculate DOM diff from previous state."""
        prev_hash = self._dom_cache.get(tab_id)
        curr_hash = current_dom.get("html_hash")
        
        if prev_hash == curr_hash:
            return None  # No change
        
        self._dom_cache[tab_id] = curr_hash
        return {
            "changed": True,
            "new_hash": curr_hash,
            "element_count": current_dom.get("element_count", 0),
        }

# ============================================================================
# SCREENSHOT STREAMING
# ============================================================================

class ScreenshotStreamer:
    """Stream screenshots from browser pages."""
    
    def __init__(self, quality: int = 80, max_width: int = 1280):
        self.quality = quality
        self.max_width = max_width
    
    async def capture(self, page: Page, full_page: bool = False) -> Optional[bytes]:
        """Capture screenshot as JPEG bytes."""
        try:
            screenshot = await page.screenshot(
                type="jpeg",
                quality=self.quality,
                full_page=full_page,
            )
            return screenshot
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None
    
    async def capture_element(self, page: Page, selector: str) -> Optional[bytes]:
        """Screenshot specific element."""
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.screenshot(type="jpeg", quality=self.quality)
            return None
        except Exception as e:
            logger.error(f"Element screenshot failed: {e}")
            return None

# ============================================================================
# BROWSER SESSION MANAGER
# ============================================================================

class BrowserSessionManager:
    """Manage Playwright browser sessions."""
    
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self._playwright = None
        self._lock = asyncio.Lock()
        self.dom_sync = DomSynchronizer()
        self.screenshot_streamer = ScreenshotStreamer()
        self._streaming_tasks: Dict[str, asyncio.Task] = {}
    
    async def _ensure_playwright(self):
        """Initialize Playwright if not already done."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")
        
        if self._playwright is None:
            self._playwright = await async_playwright().start()
    
    async def create_session(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        viewport: Optional[Dict[str, int]] = None,
        session_id: Optional[str] = None,
    ) -> BrowserSession:
        """Create new browser session."""
        await self._ensure_playwright()
        
        sid = session_id or f"browser-{uuid.uuid4().hex[:12]}"
        vp = viewport or {"width": 1280, "height": 720}
        
        # Launch browser
        browser_launcher = getattr(self._playwright, browser_type, self._playwright.chromium)
        browser = await browser_launcher.launch(headless=headless)
        context = await browser.new_context(viewport=vp)
        
        # Create initial page
        page = await context.new_page()
        tab_id = f"tab-{uuid.uuid4().hex[:8]}"
        
        session = BrowserSession(
            session_id=sid,
            browser_type=browser_type,
            headless=headless,
            viewport=vp,
            browser=browser,
            context=context,
            pages={tab_id: page},
            tabs={
                tab_id: TabState(
                    tab_id=tab_id,
                    url="about:blank",
                    viewport_width=vp["width"],
                    viewport_height=vp["height"],
                )
            },
        )
        
        async with self._lock:
            self.sessions[sid] = session
        
        # Setup event listeners
        await self._setup_page_listeners(session, page, tab_id)
        
        logger.info(f"Browser session created: {sid} ({browser_type}, headless={headless})")
        return session
    
    async def _setup_page_listeners(self, session: BrowserSession, page: Page, tab_id: str):
        """Setup Playwright event listeners."""
        
        # Console messages
        page.on("console", lambda msg: asyncio.create_task(
            self._handle_console(session, tab_id, msg)
        ))
        
        # Dialogs
        page.on("dialog", lambda dialog: asyncio.create_task(
            self._handle_dialog(session, tab_id, dialog)
        ))
        
        # Downloads
        page.on("download", lambda download: asyncio.create_task(
            self._handle_download(session, tab_id, download)
        ))
        
        # Page errors
        page.on("pageerror", lambda err: logger.error(f"Page error: {err}"))
        
        # Navigation
        page.on("framenavigated", lambda frame: asyncio.create_task(
            self._handle_navigation(session, tab_id, frame)
        ))
    
    async def _handle_console(self, session: BrowserSession, tab_id: str, msg):
        """Handle console message."""
        event = BrowserEvent(
            event_type=BrowserEventType.CONSOLE,
            timestamp=datetime.utcnow(),
            session_id=session.session_id,
            tab_id=tab_id,
            data={
                "type": msg.type,
                "text": msg.text,
                "location": msg.location,
            },
        )
        await self._broadcast_event(session, event)
        if session.recording:
            session.events.append(event)
    
    async def _handle_dialog(self, session: BrowserSession, tab_id: str, dialog):
        """Handle dialog (auto-dismiss for streaming)."""
        await dialog.dismiss()
    
    async def _handle_download(self, session: BrowserSession, tab_id: str, download):
        """Handle file download."""
        path = await download.path()
        download_info = {
            "url": download.url,
            "suggested_filename": download.suggested_filename,
            "path": str(path) if path else None,
        }
        session.downloads.append(download_info)
        
        event = BrowserEvent(
            event_type=BrowserEventType.DOWNLOAD,
            timestamp=datetime.utcnow(),
            session_id=session.session_id,
            tab_id=tab_id,
            data=download_info,
        )
        await self._broadcast_event(session, event)
    
    async def _handle_navigation(self, session: BrowserSession, tab_id: str, frame):
        """Handle frame navigation."""
        if frame.page != session.pages.get(tab_id):
            return
        
        url = frame.url
        title = await frame.title() if frame.page else ""
        
        # Update tab state
        if tab_id in session.tabs:
            session.tabs[tab_id].url = url
            session.tabs[tab_id].title = title
        
        event = BrowserEvent(
            event_type=BrowserEventType.NAVIGATION,
            timestamp=datetime.utcnow(),
            session_id=session.session_id,
            tab_id=tab_id,
            data={"url": url, "title": title},
        )
        await self._broadcast_event(session, event)
    
    async def new_tab(self, session_id: str, url: Optional[str] = None) -> str:
        """Create new tab in session."""
        session = self.sessions.get(session_id)
        if not session or not session.context:
            raise ValueError(f"Session not found: {session_id}")
        
        page = await session.context.new_page()
        if url:
            await page.goto(url)
        
        tab_id = f"tab-{uuid.uuid4().hex[:8]}"
        session.pages[tab_id] = page
        session.tabs[tab_id] = TabState(
            tab_id=tab_id,
            url=url or "about:blank",
        )
        
        await self._setup_page_listeners(session, page, tab_id)
        
        # Notify viewers
        event = BrowserEvent(
            event_type=BrowserEventType.TAB_CHANGE,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            data={"action": "created", "tab_id": tab_id, "url": url},
        )
        await self._broadcast_event(session, event)
        
        return tab_id
    
    async def close_tab(self, session_id: str, tab_id: str) -> bool:
        """Close tab in session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        page = session.pages.pop(tab_id, None)
        if page:
            await page.close()
        
        session.tabs.pop(tab_id, None)
        
        event = BrowserEvent(
            event_type=BrowserEventType.TAB_CHANGE,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            data={"action": "closed", "tab_id": tab_id},
        )
        await self._broadcast_event(session, event)
        return True
    
    async def navigate(self, session_id: str, tab_id: str, url: str) -> bool:
        """Navigate tab to URL."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        page = session.pages.get(tab_id)
        if not page:
            return False
        
        await page.goto(url, wait_until="networkidle")
        return True
    
    async def execute_js(
        self,
        session_id: str,
        tab_id: str,
        script: str,
    ) -> Any:
        """Execute JavaScript in tab."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        page = session.pages.get(tab_id)
        if not page:
            return None
        
        return await page.evaluate(script)
    
    async def get_page_state(self, session_id: str, tab_id: str) -> Dict[str, Any]:
        """Get current page state."""
        session = self.sessions.get(session_id)
        if not session:
            return {}
        
        page = session.pages.get(tab_id)
        if not page:
            return {}
        
        tab = session.tabs.get(tab_id)
        
        return {
            "url": page.url,
            "title": await page.title(),
            "viewport": tab.viewport_width if tab else 0,
            "mouse_position": (tab.mouse_x, tab.mouse_y) if tab else (0, 0),
        }
    
    async def start_streaming(self, session_id: str):
        """Start screenshot streaming for session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.streaming = True
        task = asyncio.create_task(self._streaming_loop(session_id))
        self._streaming_tasks[session_id] = task
        return True
    
    async def stop_streaming(self, session_id: str):
        """Stop screenshot streaming."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.streaming = False
        task = self._streaming_tasks.pop(session_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        return True
    
    async def _streaming_loop(self, session_id: str):
        """Background loop to stream screenshots."""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        try:
            while session.streaming and session.active:
                for tab_id, page in list(session.pages.items()):
                    # Capture screenshot
                    screenshot = await self.screenshot_streamer.capture(page)
                    if screenshot:
                        event = BrowserEvent(
                            event_type=BrowserEventType.SCREENSHOT,
                            timestamp=datetime.utcnow(),
                            session_id=session_id,
                            tab_id=tab_id,
                            screenshot=screenshot,
                            data={"size": len(screenshot)},
                        )
                        await self._broadcast_event(session, event)
                        if session.recording:
                            session.events.append(event)
                    
                    # Capture DOM
                    dom = await self.dom_sync.capture_dom(page)
                    diff = await self.dom_sync.get_dom_diff(tab_id, dom)
                    if diff:
                        event = BrowserEvent(
                            event_type=BrowserEventType.DOM_UPDATE,
                            timestamp=datetime.utcnow(),
                            session_id=session_id,
                            tab_id=tab_id,
                            data={"diff": diff, "dom": dom},
                        )
                        await self._broadcast_event(session, event)
                
                await asyncio.sleep(session.screenshot_interval)
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Streaming error: {e}")
    
    async def _broadcast_event(self, session: BrowserSession, event: BrowserEvent):
        """Broadcast event to all viewers."""
        if not WEBSOCKETS_AVAILABLE or not session.viewers:
            return
        
        message = event.to_json()
        disconnected = set()
        
        for ws in session.viewers:
            try:
                await ws.send(message)
            except Exception:
                disconnected.add(w
