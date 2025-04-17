import asyncio
from typing import Dict, List, Any
from fastapi import WebSocket, status
from starlette.websockets import WebSocketState
import json

class ConnectionManager:
    def __init__(self):
        # Dictionary to hold active connections: {channel_id: [websockets]}
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, channel_id: int, websocket: WebSocket):
        """Accepts a new websocket connection and adds it to the channel's list."""
        await websocket.accept()
        if channel_id not in self.active_connections:
            self.active_connections[channel_id] = []
        self.active_connections[channel_id].append(websocket)
        print(f"WebSocket connected. Channel {channel_id} has {len(self.active_connections[channel_id])} connections.")

    def disconnect(self, channel_id: int, websocket: WebSocket):
        """Removes a websocket connection from the channel's list."""
        if channel_id in self.active_connections:
            try:
                self.active_connections[channel_id].remove(websocket)
                print(f"WebSocket disconnected. Channel {channel_id} has {len(self.active_connections[channel_id])} connections remaining.")
                # Clean up empty channel lists
                if not self.active_connections[channel_id]:
                    del self.active_connections[channel_id]
                    print(f"Channel {channel_id} has no active connections, removing from manager.")
            except ValueError:
                # Handle case where websocket might already be removed
                print(f"Warning: WebSocket not found in channel {channel_id} list during disconnect.")
        else:
            print(f"Warning: Channel {channel_id} not found in manager during disconnect.")


    async def broadcast(self, channel_id: int, message_data: Dict[str, Any]):
        """Broadcasts a message (as JSON) to all connected clients in a specific channel."""
        if channel_id in self.active_connections:
            message_json = json.dumps(message_data) # Prepare JSON string once
            connections = self.active_connections[channel_id]
            print(f"Broadcasting to {len(connections)} connections in channel {channel_id}: {message_json}")

            # Use asyncio.gather for concurrent sending
            results = await asyncio.gather(
                *(self._send_personal_message_json(websocket, message_json) for websocket in connections),
                return_exceptions=True # Capture exceptions instead of stopping the broadcast
            )

            # Optional: Handle exceptions during broadcast (e.g., client disconnected abruptly)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    websocket = connections[i]
                    print(f"Error sending message to websocket {websocket.client}: {result}")
                    # self.disconnect(channel_id, websocket) # Be careful

    async def _send_personal_message_json(self, websocket: WebSocket, message_json: str):
        """Helper to send JSON string to a single websocket, handling potential closed states."""
        try:
            # Check state before sending, though errors can still happen race-condition wise
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(message_json)
            else:
                 print(f"WebSocket {websocket.client} is not connected, skipping send.")
        except Exception as e:
             print(f"Failed to send message to {websocket.client}: {e}")
             # Raise the exception so asyncio.gather can capture it
             raise




manager = ConnectionManager()
