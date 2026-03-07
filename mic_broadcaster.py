#!/usr/bin/env python3
"""
Audio Microphone Broadcaster using ZMQ
Captures audio from the microphone and broadcasts it to a ZMQ server.
"""

import zmq
import pyaudio
import sys
import signal

# Configuration
SERVER_ADDRESS = "tcp://127.0.0.1:5555"  # Change this to your server address
CHUNK_SIZE = 1024  # Audio chunk size
FORMAT = pyaudio.paInt16  # Audio format
CHANNELS = 1  # Mono
RATE = 16000  # Sample rate in Hz

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nShutting down...")
    sys.exit(0)

def main():
    # Setup ZMQ
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)  # Use PUSH for broadcasting to server
    # Alternatively, use zmq.PUB for PUB/SUB pattern
    # socket = context.socket(zmq.PUB)

    socket.connect(SERVER_ADDRESS)

    # Setup PyAudio
    audio = pyaudio.PyAudio()

    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )

    print(f"Starting audio broadcast to {SERVER_ADDRESS}")
    print(f"Sample rate: {RATE} Hz, Channels: {CHANNELS}, Chunk size: {CHUNK_SIZE}")
    print("Press Ctrl+C to stop...")

    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            # Read audio data from microphone
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)

            # Send to ZMQ server
            socket.send(data)

    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        stream.stop_stream()
        stream.close()
        audio.terminate()
        socket.close()
        context.term()
        print("Audio broadcast stopped.")

if __name__ == "__main__":
    main()
