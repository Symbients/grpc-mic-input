#!/usr/bin/env python3
"""
gRPC Audio Input Server.
Captures audio from microphone and streams it to connected clients via gRPC.
Listens on port 6666 following the AudioInputService specification.
"""

import asyncio
import pyaudio
from concurrent import futures
import grpc

from orchestrator.v1 import audio_input_pb2, audio_input_pb2_grpc, common_pb2


class AudioInputServicer(audio_input_pb2_grpc.AudioInputServiceServicer):
    """gRPC servicer for audio input streaming."""

    async def Listen(self, request, context):
        """
        Stream audio chunks from the microphone to the client.

        Args:
            request: ListenRequest with optional AudioConfig
            context: gRPC context

        Yields:
            CapturedAudioChunk messages with audio data
        """
        # Get config from request or use defaults
        config = request.config
        sample_rate = config.sample_rate if config.sample_rate else 24000
        channels = config.channels if config.channels else 1
        chunk_size = 4096  # Samples per chunk

        # Initialize PyAudio
        audio = pyaudio.PyAudio()

        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                frames_per_buffer=chunk_size
            )

            print(f"Started audio capture: {sample_rate}Hz, {channels} channel(s)")

            loop = asyncio.get_event_loop()
            sequence = 0
            try:
                while True:
                    # Run blocking mic read in a thread to not block the event loop
                    data = await loop.run_in_executor(
                        None, lambda: stream.read(chunk_size, exception_on_overflow=False)
                    )

                    chunk = common_pb2.AudioChunk(
                        audio_data=data,
                        sequence=sequence,
                        is_final=False
                    )

                    captured_chunk = audio_input_pb2.CapturedAudioChunk(chunk=chunk)
                    yield captured_chunk

                    sequence += 1

            except asyncio.CancelledError:
                print("Audio stream cancelled by client")
            finally:
                stream.stop_stream()
                stream.close()

        except Exception as e:
            print(f"Error in audio capture: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Audio error: {e}")
        finally:
            audio.terminate()


async def serve():
    """Start the gRPC server on port 6666."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    audio_input_pb2_grpc.add_AudioInputServiceServicer_to_server(
        AudioInputServicer(), server
    )

    server.add_insecure_port("[::]:6666")
    print("Starting Audio Input Server on port 6666...")

    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
