import pvporcupine
import pyaudio
import struct
import os
import whisper
import numpy as np
import soundfile as sf
import io
import time
import requests
import wave
import signal
import sys
import asyncio
import edge_tts
import playsound
import tempfile

# LOAD WHISPER MODEL
whisper_model = whisper.load_model("small")

# CONSTANTS
CHUNK_DURATION = 0.5
SILENCE_THRESHOLD = 1000
SILENCE_DURATION = 1.0

# CTRL + C HANDLER
def handle_interrupt(sig, frame):
    print("\n👋 Exiting cleanly...")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_interrupt)

# TEXT TO SPEECH (INDIAN MALE VOICE)
async def speak_async(text):

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        temp_filename = tmp_file.name

    communicate = edge_tts.Communicate(
        text,
        voice="en-IN-PrabhatNeural",
        rate="+5%",
        pitch="-2Hz"
    )

    await communicate.save(temp_filename)

    playsound.playsound(temp_filename)

    time.sleep(0.2)
    os.remove(temp_filename)


def speak(text):
    print("🗣️ Speaking...")
    asyncio.run(speak_async(text))

# RECORD UNTIL SILENCE
def record_command(pa, sample_rate, chunk_size):

    stream = pa.open(
        rate=sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=chunk_size
    )

    print("🎙️ Listening for command...")
    frames = []

    silence_chunks = int(SILENCE_DURATION / (chunk_size / sample_rate))
    silent_chunks = 0

    try:
        while True:
            data = stream.read(chunk_size, exception_on_overflow=False)
            frames.append(data)

            audio_np = np.frombuffer(data, dtype=np.int16)
            volume = np.abs(audio_np).mean()

            if volume < SILENCE_THRESHOLD:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks > silence_chunks:
                print("🔇 Silence detected.")
                break
    finally:
        stream.stop_stream()
        stream.close()

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))

    wav_buffer.seek(0)
    return wav_buffer

# TRANSCRIBE USING WHISPER
def transcribe_audio(wav_buffer):

    audio_array, sample_rate = sf.read(wav_buffer, dtype="float32")

    if len(audio_array.shape) > 1:
        audio_array = np.mean(audio_array, axis=1)

    if sample_rate != 16000:
        import librosa
        audio_array = librosa.resample(audio_array, orig_sr=sample_rate, target_sr=16000)

    audio_array = whisper.pad_or_trim(audio_array)
    mel = whisper.log_mel_spectrogram(audio_array).to(whisper_model.device)

    options = whisper.DecodingOptions(language="en", fp16=False)
    result = whisper.decode(whisper_model, mel, options)

    return result.text.strip()

# OLLAMA AI RESPONSE
def send_to_ollama(prompt):

    print(f"🤖 Sending to Ollama: {prompt}")

    url = "http://127.0.0.1:11434/api/generate"

    final_prompt = f"""<|system|>
You are Robo, a voice assistant.
Give a short answer in one sentences only.
<|user|>
{prompt}
<|assistant|>
"""

    response = requests.post(
        url,
        json={
            "model": "tinyllama",
            "prompt": final_prompt,
            "stream": False,
            "options": {
                "num_predict": 60,
                "temperature": 0.5
            }
        }
    )

    if response.ok:
        reply = response.json()["response"].strip()
        print(f"🧠 Robo: {reply}")
        speak(reply)
    else:
        print("❌ Ollama error")

# MAIN
def main():

    porcupine = pvporcupine.create(
        access_key=os.environ["PORCUPINE_ACCESS_KEY"],
        keyword_paths=["hey-robo_en_windows_v4_0_0.ppn"],
        sensitivities=[0.7]
    )

    pa = pyaudio.PyAudio()

    print("👂 Listening for wake word...")

    try:
        while True:

            stream = pa.open(
                rate=porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=porcupine.frame_length
            )

            try:
                while True:
                    pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
                    pcm_unpacked = struct.unpack_from(
                        "h" * porcupine.frame_length, pcm
                    )

                    if porcupine.process(pcm_unpacked) >= 0:
                        print("✅ Wake word detected!")
                        break

            finally:
                stream.stop_stream()
                stream.close()

            raw_audio = record_command(
                pa,
                porcupine.sample_rate,
                int(porcupine.sample_rate * CHUNK_DURATION)
            )

            try:
                transcript = transcribe_audio(raw_audio)

                if transcript:
                    print(f"🗣️ You said: {transcript}")
                    lower_text = transcript.lower()

                    if ("introduce" in lower_text or "yourself" in lower_text or "yourselves" in lower_text or "your self" in lower_text) or \
                        ("who" in lower_text and "you" in lower_text):
                        reply = ("I am Neo the Robot, created by the BCA Department of "
                                 "Srimath Sivagnana Baalaya Swamigal Tamil,Arts,Science College  "
                                 "for the Science Day exhibition, "
                                 "I am a smart, voice-controlled robot. When you speak, I listen. I process your command. Then I respond in real time. Thank you for interacting with me.")
                        print(f"🧠 Robo: {reply}")
                        speak(reply)

                    elif "course" in lower_text or "courses" in lower_text:
                        reply = ("Our college offers BCA, BSc Computer Science, "
                                 "BCom Computer Applications, Chemistry, "
                                 "BA Tamil Literature and English.")
                        print(f"🧠 Robo: {reply}")
                        speak(reply)

                    elif ("hod" in lower_text or "bca" in lower_text or "department" in lower_text) or \
                        ("head of department" in lower_text or "hod of bca" in lower_text):
                        reply = "The Head of the BCA Department is Doctor Anuraatha Ma'am."
                        print(f"🧠 Robo: {reply}")
                        speak(reply)

                    elif ("college" in lower_text and "principal" in lower_text ):
                        reply = "The principal of our college is Doctor S. Thirunaavukkarasu."
                        print(f"🧠 Robo: {reply}")
                        speak(reply)
                    else:
                        send_to_ollama(transcript)

                else:
                    speak("Please try again.")

            except Exception as e:
                print(f"❌ Error: {e}")

    except KeyboardInterrupt:
        print("👋 Exiting...")

    finally:
        pa.terminate()
        porcupine.delete()


if __name__ == "__main__":
    main()