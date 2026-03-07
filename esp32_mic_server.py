#!/usr/bin/env python3
"""
ESP32 Mic Forward Server

Listens for mic audio stream on port 6666 and forwards it to all connected ESP32s.
ESP32s register on port 8888 and receive audio stream on port 7777.
"""

import asyncio
import websockets
import logging

# Define Ports
ESP_REGISTER_PORT = 8888  # ESP32s connect here to register
MIC_INPUT_PORT = 6666     # Mic stream connects here
STREAM_PORT = 7777        # Audio is forwarded to ESP32s here

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

agents = []  # All connected ESP32s with their registration sockets
stream_clients = []  # All connected stream clients (port 7777)

def register_esp(esp_id, ws):
    logging.info(f"Registering ESP id: {esp_id}")
    agents.append({"id": esp_id, "ws": ws})

def unregister_esp(esp_id):
    logging.info(f"Unregistering ESP {esp_id}")
    for i, a in enumerate(agents):
        if a["id"] == esp_id:
            agents.pop(i)
            break

async def handle_esp_registration(websocket):
    """Handle ESP32 registration and keep connection alive."""
    esp_id = await websocket.recv()
    logging.info(f"ESP32 connected on registration port: {esp_id}")
    register_esp(esp_id, websocket)

    try:
        # Keep connection alive, receive any messages from ESP
        async for msg in websocket:
            logging.debug(f"Received message from ESP {esp_id}: {len(msg)} bytes")
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"ESP {esp_id} disconnected from registration port")
    finally:
        unregister_esp(esp_id)

async def handle_esp_stream(websocket):
    """
    Handle ESP32 stream port connection.
    ESP connects here to receive audio data.
    No ID exchange - just keep connection open for streaming.
    """
    logging.info(f"ESP32 connected on stream port (total: {len(stream_clients) + 1})")
    stream_clients.append(websocket)

    try:
        # Keep connection alive - ESP will receive audio through this socket
        await asyncio.Future()
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"ESP32 stream disconnected (remaining: {len(stream_clients) - 1})")
    finally:
        if websocket in stream_clients:
            stream_clients.remove(websocket)

async def broadcast_to_esps(audio_data):
    """Send audio data to all connected stream clients (port 7777)."""
    if not stream_clients:
        return 0

    sent_count = 0
    failed = []
    for ws in stream_clients:
        try:
            await ws.send(audio_data)
            sent_count += 1
        except Exception as e:
            logging.error(f"Error sending to stream client: {e}")
            failed.append(ws)

    # Remove failed connections
    for ws in failed:
        if ws in stream_clients:
            stream_clients.remove(ws)

    return sent_count

async def send_mode_to_all_esps(mode):
    """Send MODE command to all ESPs via their registration socket."""
    for agent in agents:
        ws = agent.get("ws")
        if ws:
            try:
                await ws.send(str(mode))
                logging.info(f"Sent MODE {mode} to ESP {agent['id']}")
            except Exception as e:
                logging.error(f"Error sending mode to ESP {agent['id']}: {e}")

async def handle_mic_stream(websocket):
    """Receive mic stream on port 6666 and forward to all ESP32s."""
    logging.info("Mic stream connected on port 6666")

    # Send MODE 3 (speak) to all ESPs
    logging.info("Sending MODE 3 to all ESPs...")
    await send_mode_to_all_esps(3)

    # Wait a moment for ESPs to connect to stream port
    logging.info("Waiting for ESPs to connect to stream port...")
    await asyncio.sleep(2)

    chunk_count = 0
    try:
        async for audio_chunk in websocket:
            if audio_chunk:
                chunk_count += 1
                sent = await broadcast_to_esps(audio_chunk)
                if chunk_count % 100 == 0:  # Log every 100 chunks to avoid spam
                    logging.info(f"Forwarded {chunk_count} chunks, last sent to {sent} ESP(s), chunk size: {len(audio_chunk)} bytes")
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"Mic stream disconnected after {chunk_count} chunks")
    except Exception as e:
        logging.error(f"Error in mic stream: {e}")

async def main():
    logging.info("=" * 50)
    logging.info("ESP32 Mic Forward Server")
    logging.info("=" * 50)
    logging.info(f"  ESP32 registration port: {ESP_REGISTER_PORT}")
    logging.info(f"  ESP32 stream port:       {STREAM_PORT}")
    logging.info(f"  Mic input port:          {MIC_INPUT_PORT}")
    logging.info("=" * 50)

    async with websockets.serve(handle_esp_registration, '', ESP_REGISTER_PORT, ping_interval=None):
        async with websockets.serve(handle_esp_stream, '', STREAM_PORT, ping_interval=None):
            async with websockets.serve(handle_mic_stream, '', MIC_INPUT_PORT, ping_interval=None):
                logging.info("All servers started. Waiting for connections...")
                await asyncio.Future()  # run forever

if __name__ == '__main__':
    asyncio.run(main())
