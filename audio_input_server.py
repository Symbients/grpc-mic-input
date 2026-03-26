#!/usr/bin/env python3
"""
gRPC Audio Input Server.
Captures audio from microphone and streams it to connected clients via gRPC.
Listens on port 6666 following the AudioInputService specification.
"""

import asyncio
import struct
import ctypes
import pyaudio
from concurrent import futures
import grpc

from orchestrator.v1 import audio_input_pb2, audio_input_pb2_grpc, common_pb2


# Suppress noisy ALSA/JACK warnings on Linux (especially Raspberry Pi)
# Must be called before any PyAudio instantiation
try:
    _ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )

    def _null_error_handler(filename, line, function, err, fmt):
        pass

    _c_null_error_handler = _ERROR_HANDLER_FUNC(_null_error_handler)
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(_c_null_error_handler)
except OSError:
    pass  # Not on Linux / ALSA not available


class AudioInputServicer(audio_input_pb2_grpc.AudioInputServiceServicer):
    """gRPC servicer for audio input streaming."""

    async def GetConfig(self, request, context):
        """Return the audio configuration of this input device."""
        config = common_pb2.AudioConfig(sample_rate=24000, channels=1)
        return common_pb2.GetConfigResponse(config=config)

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

                    # Convert int16 PCM bytes to normalized f32 samples (-1.0..1.0)
                    int16_samples = struct.unpack(f'<{len(data)//2}h', data)
                    float_samples = [s / 32768.0 for s in int16_samples]

                    chunk = common_pb2.AudioChunk(
                        samples=float_samples,
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
            # Brief pause lets the executor thread finish its blocked read
            # before we destroy the PyAudio instance (avoids segfault)
            await asyncio.sleep(0.2)
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
