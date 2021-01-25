from howl.context import InferenceContext
import logging
import time
from typing import Callable

import numpy as np
import pyaudio
import torch
from howl.model.inference import InferenceEngine


class HowlClient:
    """
    A client for serving Howl models. Users can provide custom listener callbacks
    when a wake word is detected using the `add_listener` method.

    The `from_pretrained` method allows users to directly load a pretrained model by name,
    such as "hey_fire_fox", if the model is not provided upon initialization.
    """

    def __init__(self,
                 engine: InferenceEngine = None,
                 context: InferenceContext = None,
                 device: int = -1,
                 chunk_size: int = 500):
        """
        Initializes the client.

            Parameters:
                engine (InferenceEngine): An InferenceEngine for processing audio input, provided
                                          on initialization or by loading a pretrained model.
                context (InferenceContext): An InferenceContext object containing vocab, provided
                                            on initialization or by loading a pretrained model.
                device (int): Device for CPU/GPU support. Defaults to -1 for running on CPU,
                              positive values will run the model on the associated CUDA device.
                chunk_size (int): Number of frames per buffer for audio.
        """
        self.listeners = []
        self.chunk_size = chunk_size
        self.device = self._get_device(device)

        self.engine: InferenceEngine = engine
        self.ctx: InferenceContext = context

        self._audio = pyaudio.PyAudio()
        self._audio_buf = []
        self._audio_buf_len = 16
        self._audio_float_size = 32767
        self.last_data = np.zeros(self.chunk_size)

    @staticmethod
    def list_pretrained(self):
        """Show a list of available pretrained models"""
        print(torch.hub.list('castorini/howl:howl-pip'))

    def _get_device(device: int):
        if device == -1:
            return torch.device('cpu')
        else:
            return torch.device('cuda:{}'.format(device))

    def _on_audio(self, in_data):
        data_ok = (in_data, pyaudio.paContinue)
        self.last_data = in_data
        self._audio_buf.append(in_data)
        if len(self._audio_buf) != self._audio_buf_len:
            return data_ok

        audio_data = b''.join(self._audio_buf)
        self._audio_buf = self._audio_buf[2:]
        arr = self._normalize_audio(audio_data)
        inp = torch.from_numpy(arr).float().to(self.device)

        # Inference from input sequence
        if self.engine.infer(inp):
            phrase = ' '.join(self.ctx.vocab[x]
                              for x in self.engine.sequence).title()
            logging.info(f'{phrase} detected', end='\r')
            # Execute user-provided listener callbacks
            for lis in self.listeners:
                lis(self.engine.sequence)

        return data_ok

    def _normalize_audio(self, audio_data):
        return np.frombuffer(audio_data, dtype=np.int16).astype(np.float) / self._audio_float_size

    def start(self):
        """Start the audio stream for inference"""
        if self.engine is None:
            raise AttributeError(
                'Please provide an InferenceEngine or initialize using from_pretrained.'
            )
        if self.ctx is None:
            raise AttributeError(
                'Please provide an InferenceContext or initialize using from_pretrained.'
            )

        chosen_idx = 0
        for idx in range(self._audio.get_device_count()):
            info = self._audio.get_device_info_by_index(idx)
            if info['name'] == 'pulse':
                chosen_idx = idx
                break

        stream = self._audio.open(format=pyaudio.paInt16,
                                  channels=1,
                                  rate=16000,
                                  input=True,
                                  input_device_index=chosen_idx,
                                  frames_per_buffer=self.chunk_size,
                                  stream_callback=self._on_audio)
        self.stream = stream
        stream.start_stream()

    def join(self):
        """Block while the audio inference stream is active"""
        while self.stream.is_active():
            time.sleep(0.1)

    def from_pretrained(self, name: str):
        """Load a pretrained model using the provided name"""
        engine, ctx = torch.hub.load('castorini/howl:howl-pip', name)
        self.engine = engine.to(self.device)
        self.ctx = ctx

    def add_listener(self, listener: Callable):
        """Add a listener callback to be executed when a sequence is detected"""
        self.listeners.append(listener)
