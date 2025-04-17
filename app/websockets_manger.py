import asyncio
import json
import logging # Use logging module
from typing import Dict, List, Any

from fastapi import WebSocket, status
from starlette.websockets import WebSocketState, WebSocketDisconnect # Ensure import

logger = logging.getLogger(__name__) # Create a logger instance

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {} # {channel_id: [websockets]}
        logger.info("ConnectionManager initialized.")

    async def connect(self, channel_id: int, websocket: WebSocket):
        """Accepts a new websocket connection."""
        await websocket.accept()
        if channel_id not in self.active_connections:
            self.active_connections[channel_id] = []
        self.active_connections[channel_id].append(websocket)
        logger.info(f"WS connected: {websocket.client} to channel {channel_id}. Total connections in channel: {len(self.active_connections[channel_id])}")

    def disconnect(self, channel_id: int, websocket: WebSocket):
        """Removes a websocket connection."""
        if channel_id in self.active_connections:
            try:
                self.active_connections[channel_id].remove(websocket)
                remaining = len(self.active_connections[channel_id])
                logger.info(f"WS disconnected: {websocket.client} from channel {channel_id}. Remaining connections: {remaining}")
                if not self.active_connections[channel_id]:
                    del self.active_connections[channel_id]
                    logger.info(f"Channel {channel_id} has no active connections, removing from manager.")
            except ValueError:
                logger.warning(f"WS disconnect: WebSocket {websocket.client} not found in channel {channel_id} list.")
        else:
            logger.warning(f"WS disconnect: Channel {channel_id} not found in manager for client {websocket.client}.")

    async def broadcast(self, channel_id: int, message_data: Dict[str, Any]):
        """Broadcasts a message dictionary (as JSON) to all connected clients in a specific channel."""
        if channel_id in self.active_connections:
            # message_data should be a serializable dict (e.g., from model_dump)
            try:
                message_json = json.dumps(message_data) # Prepare JSON string once
            except TypeError as e:
                logger.error(f"Failed to serialize message data for broadcast in channel {channel_id}: {e} - Data: {message_data}", exc_info=True)
                return # Don't broadcast unserializable data

            connections = list(self.active_connections[channel_id]) # Copy list for safe iteration
            if not connections:
                logger.info(f"No active connections in channel {channel_id} to broadcast to.")
                return

            logger.debug(f"Broadcasting to {len(connections)} connections in channel {channel_id}: {message_json}")

            results = await asyncio.gather(
                *(self._send_personal_message_json(websocket, message_json, channel_id) for websocket in connections),
                return_exceptions=True # Capture exceptions
            )

            # Handle exceptions during broadcast
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    websocket = connections[i] # Get corresponding websocket
                    # Check if websocket is still in the list (might have disconnected concurrently)
                    if channel_id in self.active_connections and websocket in self.active_connections[channel_id]:
                        logger.error(f"Error sending message to WS {websocket.client} in channel {channel_id}: {result}. Disconnecting.")
                        self.disconnect(channel_id, websocket) # Remove from active list first
                        try:
                            if websocket.client_state != WebSocketState.DISCONNECTED:
                                await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
                        except RuntimeError as close_error:

                            logger.warning(f"Error closing websocket {websocket.client} after send error: {close_error}")
                    else:
                         logger.warning(f"Error sending message to WS {websocket.client} in channel {channel_id}, but it already disconnected.")


    async def _send_personal_message_json(self, websocket: WebSocket, message_json: str, channel_id: int):
        """Helper to send JSON string to a single websocket."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(message_json)
            else:
                 logger.warning(f"WebSocket {websocket.client} in channel {channel_id} is not connected, skipping send.")
        except Exception as e:
             # Log the error here before raising it
             logger.error(f"Failed to send message to {websocket.client} in channel {channel_id}: {e}", exc_info=False) # exc_info=False to avoid duplicate stack trace from gather
             raise

manager = ConnectionManager()
