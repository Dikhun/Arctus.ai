#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Terminal Streaming Engine
=============================================================
Real-time terminal streaming engine with WebSocket support, PTY integration,
ANSI color support, session recording, replay, and multi-viewer capabilities.
"""

from __future__ import annotations

import asyncio
import base64
import fcntl
import json
import logging
import os
import pty
import select
import struct
import termios
import tty
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# WebSocket support
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger("arctus.terminal")
logger.setLevel(logging.DEBUG)

# ============================================================================
# DATA MODELS
# ============================================================================

class TerminalEventType(Enum):
    OUTPUT = auto()
    RESIZE = auto()
    CURSOR_MOVE = auto()
    COMMAND_START = auto()
    COMMAND_END = auto()
    ERROR = auto()
    SESSION_CLOSE = auto()

@dataclass(slots=True)
class TerminalEvent:
    """Single terminal event for streaming and recording."""
    event_type: TerminalEventType
    timestamp: datetime
    session_id: str
    data: bytes = b""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        """Serialize to JSON for WebSocket transmission."""
        return json.dumps({
            "type": self.event_type.name,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "data": base64.b64encode(self.data).decode() if self.data else "",
            "metadata": self.metadata,
        })
    
    @classmethod
    def from_json(cls, raw: str) -> TerminalEvent:
        data = json.loads(raw)
        return cls(
            event_type=TerminalEventType[data["type"]],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_id=data["session_id"],
            data=base64.b64decode(data["data"]) if data.get("data") else b"",
            metadata=data.get("metadata", {}),
        )

@dataclass(slots=True)
class TerminalDimensions:
    """Terminal size configuration."""
    rows: int = 24
    cols: int = 80
    width_px: int = 0
    height_px: int = 0
    
    def to_pty_format(self) -> struct.Struct:
        return struct.pack("HHHH", self.rows, self.cols, self.width_px, self.height_px)

@dataclass
class TerminalSession:
    """Active terminal session state."""
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    dimensions: TerminalDimensions = field(default_factory=TerminalDimensions)
    command_history: deque = field(default_factory=lambda: deque(maxlen=1000))
    output_buffer: deque = field(default_factory=lambda: deque(maxlen=10000))
    viewers: Set[WebSocketServerProtocol] = field(default_factory=set)
    recording: bool = False
    recording_path: Optional[Path] = None
    pty_fd: Optional[int] = None
    pid: Optional[int] = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ANSI state
    current_cursor_row: int = 0
    current_cursor_col: int = 0
    ansi_buffer: bytes = b""

# ============================================================================
# ANSI PROCESSOR
# ============================================================================

class AnsiProcessor:
    """Process ANSI escape sequences for terminal emulation."""
    
    # Common ANSI patterns
    ESC = b"\x1b"
    CSI = b"\x1b["
    OSC = b"\x1b]"
    
    # SGR (Select Graphic Rendition) colors
    COLORS = {
        30: "black", 31: "red", 32: "green", 33: "yellow",
        34: "blue", 35: "magenta", 36: "cyan", 37: "white",
        90: "bright_black", 91: "bright_red", 92: "bright_green",
        93: "bright_yellow", 94: "bright_blue", 95: "bright_magenta",
        96: "bright_cyan", 97: "bright_white",
    }
    
    def __init__(self):
        self.current_style: Dict[str, Any] = {
            "fg": None, "bg": None,
            "bold": False, "italic": False,
            "underline": False, "strikethrough": False,
        }
    
    def process(self, data: bytes) -> List[Dict[str, Any]]:
        """
        Process raw terminal data into styled segments.
        Returns list of {text, style} dicts.
        """
        segments = []
        i = 0
        current_text = ""
        
        while i < len(data):
            if data[i:i+2] == self.CSI:
                # Save current text
                if current_text:
                    segments.append({"text": current_text, "style": dict(self.current_style)})
                    current_text = ""
                
                # Parse CSI sequence
                end = i + 2
                while end < len(data) and data[end] not in b"@ABCDEFGHILMNOPSTXZ`abcdefghilmnprsu":
                    end += 1
                if end < len(data):
                    end += 1  # Include command char
                
                seq = data[i:end]
                self._apply_csi(seq)
                i = end
            else:
                char = data[i:i+1]
                if char == b"\n":
                    if current_text:
                        segments.append({"text": current_text, "style": dict(self.current_style)})
                        current_text = ""
                    segments.append({"text": "\n", "style": {"type": "newline"}})
                elif char == b"\r":
                    pass  # Ignore CR
                elif char == b"\x07":
                    segments.append({"text": "", "style": {"type": "bell"}})
                else:
                    try:
                        current_text += char.decode("utf-8", errors="replace")
                    except:
                        current_text += "?"
                i += 1
        
        if current_text:
            segments.append({"text": current_text, "style": dict(self.current_style)})
        
        return segments
    
    def _apply_csi(self, seq: bytes):
        """Apply CSI escape sequence."""
        # Extract parameters and command
        params = seq[2:-1].decode("ascii", errors="replace")
        cmd = seq[-1:].decode("ascii")
        
        if cmd == "m":  # SGR
            for param in params.split(";"):
                if not param:
                    continue
                try:
                    code = int(param)
                    if code == 0:
                        self.current_style = {
                            "fg": None, "bg": None,
                            "bold": False, "italic": False,
                            "underline": False, "strikethrough": False,
                        }
                    elif code == 1:
                        self.current_style["bold"] = True
                    elif code == 3:
                        self.current_style["italic"] = True
                    elif code == 4:
                        self.current_style["underline"] = True
                    elif code == 9:
                        self.current_style["strikethrough"] = True
                    elif 30 <= code <= 37:
                        self.current_style["fg"] = self.COLORS.get(code)
                    elif 40 <= code <= 47:
                        self.current_style["bg"] = self.COLORS.get(code - 10)
                    elif 90 <= code <= 97:
                        self.current_style["fg"] = self.COLORS.get(code)
                    elif 100 <= code <= 107:
                        self.current_style["bg"] = self.COLORS.get(code - 10)
                except ValueError:
                    pass
        
        elif cmd in "Hf":  # Cursor position
            pass  # Track if needed
        
        elif cmd == "J":  # Erase display
            pass
        
        elif cmd == "K":  # Erase line
            pass

# ============================================================================
# PTY MANAGER
# ============================================================================

class PtyManager:
    """Manage pseudo-terminal sessions."""
    
    def __init__(self):
        self.sessions: Dict[str, TerminalSession] = {}
        self._lock = asyncio.Lock()
        self._read_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_session(
        self,
        shell: str = "/bin/bash",
        dimensions: Optional[TerminalDimensions] = None,
        env: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
    ) -> TerminalSession:
        """Create a new PTY session."""
        sid = session_id or f"term-{uuid.uuid4().hex[:12]}"
        dims = dimensions or TerminalDimensions()
        
        # Create PTY
        pid, fd = pty.fork()
        
        if pid == 0:
            # Child process
            os.environ.update(env or {})
            # Set terminal size
            winsize = struct.pack("HHHH", dims.rows, dims.cols, 0, 0)
            fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)
            os.execv(shell, [shell])
        
        # Parent process
        os.set_blocking(fd, False)
        
        session = TerminalSession(
            session_id=sid,
            dimensions=dims,
            pty_fd=fd,
            pid=pid,
            metadata={"shell": shell, "env": env},
        )
        
        async with self._lock:
            self.sessions[sid] = session
        
        # Start reading from PTY
        task = asyncio.create_task(self._pty_reader(sid))
        self._read_tasks[sid] = task
        
        logger.info(f"PTY session created: {sid} (pid={pid})")
        return session
    
    async def _pty_reader(self, session_id: str):
        """Read output from PTY and broadcast to viewers."""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        fd = session.pty_fd
        if fd is None:
            return
        
        loop = asyncio.get_event_loop()
        buf_size = 4096
        
        try:
            while session.active:
                # Use select for non-blocking read
                readable, _, _ = select.select([fd], [], [], 0.1)
                if not readable:
                    await asyncio.sleep(0.01)
                    continue
                
                try:
                    data = os.read(fd, buf_size)
                    if not data:
                        break
                except (OSError, IOError):
                    break
                
                # Create event
                event = TerminalEvent(
                    event_type=TerminalEventType.OUTPUT,
                    timestamp=datetime.utcnow(),
                    session_id=session_id,
                    data=data,
                    metadata={"len": len(data)},
                )
                
                # Buffer output
                session.output_buffer.append(data)
                
                # Record if enabled
                if session.recording:
                    await self._record_event(session, event)
                
                # Broadcast to viewers
                await self._broadcast(session, event)
        
        except Exception as e:
            logger.error(f"PTY reader error for {session_id}: {e}")
        
        finally:
            session.active = False
            # Notify close
            close_event = TerminalEvent(
                event_type=TerminalEventType.SESSION_CLOSE,
                timestamp=datetime.utcnow(),
                session_id=session_id,
            )
            await self._broadcast(session, close_event)
            logger.info(f"PTY session ended: {session_id}")
    
    async def _broadcast(self, session: TerminalSession, event: TerminalEvent):
        """Broadcast event to all connected viewers."""
        if not WEBSOCKETS_AVAILABLE or not session.viewers:
            return
        
        message = event.to_json()
        disconnected = set()
        
        for ws in session.viewers:
            try:
                await ws.send(message)
            except Exception:
                disconnected.add(ws)
        
        # Clean up disconnected viewers
        session.viewers -= disconnected
    
    async def _record_event(self, session: TerminalSession, event: TerminalEvent):
        """Record event to session recording file."""
        if not session.recording_path:
            return
        
        loop = asyncio.get_event_loop()
        
        def _write():
            with open(session.recording_path, "a") as f:
                f.write(event.to_json() + "\n")
        
        await loop.run_in_executor(None, _write)
    
    async def write_to_session(self, session_id: str, data: bytes) -> bool:
        """Write input to PTY session."""
        session = self.sessions.get(session_id)
        if not session or session.pty_fd is None:
            return False
        
        try:
            os.write(session.pty_fd, data)
            return True
        except OSError:
            return False
    
    async def resize_session(
        self,
        session_id: str,
        dimensions: TerminalDimensions,
    ) -> bool:
        """Resize terminal session."""
        session = self.sessions.get(session_id)
        if not session or session.pty_fd is None:
            return False
        
        session.dimensions = dimensions
        winsize = struct.pack("HHHH", dimensions.rows, dimensions.cols, 0, 0)
        
        try:
            fcntl.ioctl(session.pty_fd, termios.TIOCSWINSZ, winsize)
            
            # Notify viewers
            event = TerminalEvent(
                event_type=TerminalEventType.RESIZE,
                timestamp=datetime.utcnow(),
                session_id=session_id,
                metadata={"rows": dimensions.rows, "cols": dimensions.cols},
            )
            await self._broadcast(session, event)
            return True
        except OSError:
            return False
    
    async def attach_viewer(
        self,
        session_id: str,
        websocket: WebSocketServerProtocol,
    ) -> bool:
        """Attach WebSocket viewer to session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.viewers.add(websocket)
        
        # Send buffered history
        await self._send_history(session, websocket)
        
        logger.info(f"Viewer attached to {session_id} (total: {len(session.viewers)})")
        return True
    
    async def detach_viewer(
        self,
        session_id: str,
        websocket: WebSocketServerProtocol,
    ) -> bool:
        """Detach WebSocket viewer from session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.viewers.discard(websocket)
        return True
    
    async def _send_history(
        self,
        session: TerminalSession,
        websocket: WebSocketServerProtocol,
    ):
        """Send buffered history to new viewer."""
        if not WEBSOCKETS_AVAILABLE:
            return
        
        # Send recent output
        for data in session.output_buffer:
            event = TerminalEvent(
                event_type=TerminalEventType.OUTPUT,
                timestamp=datetime.utcnow(),
                session_id=session.session_id,
                data=data,
            )
            try:
                await websocket.send(event.to_json())
            except Exception:
                break
    
    async def start_recording(
        self,
        session_id: str,
        path: Optional[Path] = None,
    ) -> Path:
        """Start recording session to file."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        record_path = path or Path(f"/tmp/arctus/recordings/{session_id}.cast")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        
        session.recording = True
        session.recording_path = record_path
        
        # Write header
        header = {
            "version": 2,
            "width": session.dimensions.cols,
            "height": session.dimensions.rows,
            "timestamp": datetime.utcnow().timestamp(),
            "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
        }
        
        with open(record_path, "w") as f:
            f.write(json.dumps(header) + "\n")
        
        return record_path
    
    async def stop_recording(self, session_id: str) -> Optional[Path]:
        """Stop recording session."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        session.recording = False
        path = session.recording_path
        session.recording_path = None
        return path
    
    async def close_session(self, session_id: str) -> bool:
        """Close terminal session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.active = False
        
        # Cancel reader task
        task = self._read_tasks.pop(session_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close PTY
        if session.pty_fd is not None:
            try:
                os.close(session.pty_fd)
            except OSError:
                pass
        
        # Kill process
        if session.pid:
            try:
                os.kill(session.pid, 9)
            except ProcessLookupError:
                pass
        
        async with self._lock:
            del self.sessions[session_id]
        
        return True
    
    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def list_sessions(self) -> List[TerminalSession]:
        """List all active sessions."""
        return list(self.sessions.values())

# ============================================================================
# SESSION REPLAY ENGINE
# ============================================================================

class SessionReplayEngine:
    """Replay recorded terminal sessions."""
    
    def __init__(self, recording_path: Path):
        self.recording_path = Path(recording_path)
        self.events: List[TerminalEvent] = []
        self._loaded = False
    
    async def load(self):
        """Load recording from file."""
        loop = asyncio.get_event_loop()
        
        def _read():
            events = []
            with open(self.recording_path, "r") as f:
                # Skip header
                header = json.loads(f.readline())
                for line in f:
                    if line.strip():
                        events.append(TerminalEvent.from_json(line))
            return events, header
        
        self.events, self.header = await loop.run_in_executor(None, _read)
        self._loaded = True
    
    async def replay(
        self,
        websocket: WebSocketServerProtocol,
        speed: float = 1.0,
        start_from: Optional[datetime] = None,
    ):
        """Replay session to WebSocket viewer."""
        if not self._loaded:
            await self.load()
        
        if not WEBSOCKETS_AVAILABLE:
            return
        
        # Filter events
        events = self.events
        if s
