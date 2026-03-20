#!/usr/bin/env python3
"""
gRPC-to-ESP32 Bridge

Connects to the gRPC AudioInputService on the Raspberry Pi to receive mic audio,
and broadcasts it to all connected ESP32s via WebSocket.

ESP32s register on port 8888 and receive audio on port 7777.
"""

import asyncio
import logging
import grpc
import websockets

from orchestrator.v1 import audio_input_pb2, audio_input_pb2_grpc

# gRPC source
GRPC_SERVER = "192.168.10.54:6666"

# WebSocket ports for ESP32s
ESP_REGISTER_PORT = 8888
STREAM_PORT = 7777

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

agents = []
stream_clients = []


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
        async for msg in websocket:
            logging.debug(f"Received message from ESP {esp_id}: {len(msg)} bytes")
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"ESP {esp_id} disconnected from registration port")
    finally:
        unregister_esp(esp_id)


async def handle_esp_stream(websocket):
    """Handle ESP32 stream port connection."""
    logging.info(f"ESP32 connected on stream port (total: {len(stream_clients) + 1})")
    stream_clients.append(websocket)

    try:
        await asyncio.Future()
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"ESP32 stream disconnected (remaining: {len(stream_clients) - 1})")
    finally:
        if websocket in stream_clients:
            stream_clients.remove(websocket)


async def broadcast_to_esps(audio_data):
    """Send audio data to all connected stream clients."""
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


async def grpc_audio_stream():
    """Connect to gRPC AudioInputService and broadcast audio to ESP32s."""
    logging.info(f"Connecting to gRPC server at {GRPC_SERVER}...")

    async with grpc.aio.insecure_channel(GRPC_SERVER) as channel:
        stub = audio_input_pb2_grpc.AudioInputServiceStub(channel)

        request = audio_input_pb2.ListenRequest(
            config={"sample_rate": 24000, "channels": 1}
        )

        logging.info("Starting audio stream from Raspberry Pi...")

        # Wait for at least one ESP to register before sending MODE 3
        logging.info("Waiting for ESP32s to register...")
        while not agents:
            await asyncio.sleep(0.5)
        logging.info(f"{len(agents)} ESP(s) registered. Sending MODE 3...")
        await send_mode_to_all_esps(3)

        # Wait for ESPs to connect to stream port after receiving MODE 3
        logging.info("Waiting for ESPs to connect to stream port...")
        await asyncio.sleep(3)
        while not stream_clients:
            await asyncio.sleep(0.5)
        logging.info(f"{len(stream_clients)} ESP(s) connected to stream port.")

        chunk_count = 0
        async for captured_chunk in stub.Listen(request):
            # Forward raw PCM bytes directly — no conversion needed
            pcm_data = captured_chunk.chunk.audio_data

            sent = await broadcast_to_esps(pcm_data)
            chunk_count += 1

            if chunk_count % 500 == 0:
                logging.info(
                    f"Forwarded {chunk_count} chunks, last sent to {sent} ESP(s), "
                    f"chunk size: {len(pcm_data)} bytes"
                )


async def main():
    logging.info("=" * 50)
    logging.info("gRPC-to-ESP32 Bridge")
    logging.info("=" * 50)
    logging.info(f"  gRPC source:             {GRPC_SERVER}")
    logging.info(f"  ESP32 registration port: {ESP_REGISTER_PORT}")
    logging.info(f"  ESP32 stream port:       {STREAM_PORT}")
    logging.info("=" * 50)

    async with websockets.serve(handle_esp_registration, '', ESP_REGISTER_PORT, ping_interval=None):
        async with websockets.serve(handle_esp_stream, '', STREAM_PORT, ping_interval=None):
            logging.info("WebSocket servers started. Waiting for ESP32 connections...")
            await grpc_audio_stream()


if __name__ == '__main__':
    asyncio.run(main())
