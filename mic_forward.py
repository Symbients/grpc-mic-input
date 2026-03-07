#!/usr/bin/env python3
"""
Simple mic capture and WebSocket forwarder.
Captures audio from microphone and sends raw PCM data to a WebSocket server.
"""

import pyaudio
import asyncio
import websockets

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024  # Buffer size
FORMAT = pyaudio.paInt16

# WebSocket target
WS_URL = "ws://192.168.10.130:6666"


async def mic_to_websocket():
    # Initialize PyAudio
    audio = pyaudio.PyAudio()

    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    print(f"Connecting to {WS_URL}...")

    try:
        async with websockets.connect(WS_URL) as ws:
            print("Connected! Streaming mic audio... (Ctrl+C to stop)")

            while True:
                # Read audio data from mic
                data = stream.read(CHUNK, exception_on_overflow=False)
                # Send as binary
                await ws.send(data)
                # Small yield to prevent blocking
                await asyncio.sleep(0)

    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()
        print("Cleaned up.")


if __name__ == "__main__":
    asyncio.run(mic_to_websocket())
