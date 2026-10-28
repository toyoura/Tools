"""Generate an English narration mp3 using the Gemini TTS API.
https://ai.google.dev/gemini-api/docs/speech-generation?hl=ja 

Usage: python tts_generate.py <output_name_without_ext> <text_file_path>
(GEMINI_API_KEY or GOOGLE_API_KEY required; ffmpeg must be on PATH)
The wav and mp3 are written to the current directory.

Samples VOICE_NAME 
https://docs.cloud.google.com/text-to-speech/docs/gemini-tts?hl=ja 
"""
import os
import subprocess
import sys
import wave

from google import genai
from google.genai import types

VOICE_NAME = "Kore"
OUT_DIR = os.getcwd()

if len(sys.argv) < 3:
    sys.exit("Usage: python tts_generate.py <output_name> <text_file_path>")

output_name = sys.argv[1]
with open(sys.argv[2], "r", encoding="utf-8") as f:
    text = f.read()

wav_path = os.path.join(OUT_DIR, f"{output_name}.wav")
mp3_path = os.path.join(OUT_DIR, f"{output_name}.mp3")

api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    sys.exit("No GEMINI_API_KEY / GOOGLE_API_KEY found in environment.")

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-2.5-flash-preview-tts",
    contents=text,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=VOICE_NAME,
                )
            )
        ),
    ),
)

audio_bytes = response.candidates[0].content.parts[0].inline_data.data

with wave.open(wav_path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(24000)
    wf.writeframes(audio_bytes)

subprocess.run(
    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
    check=True,
)

print(f"Saved: {mp3_path}")
