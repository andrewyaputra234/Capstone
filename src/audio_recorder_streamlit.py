"""
Streamlit Audio Recording Component
Live mic recording + Whisper transcription for real-time speech-to-text
"""

import streamlit as st
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

try:
    from streamlit_mic_recorder import mic_recorder
    MIC_RECORDER_AVAILABLE = True
except ImportError:
    MIC_RECORDER_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

load_dotenv()


class StreamlitAudioRecorder:
    """
    Real-time audio recording and transcription for Streamlit UI.
    Uses streamlit-mic-recorder for browser-based live mic input.
    """
    
    def __init__(self):
        """Initialize audio recorder and Whisper client."""        
        if not OPENAI_AVAILABLE:
            st.error("openai not installed. Run: pip install openai")
            raise RuntimeError("openai required")
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY not set in environment")
            raise ValueError("OPENAI_API_KEY required")
        
        self.client = OpenAI(api_key=api_key)
    
    def record_and_transcribe(self, key_suffix: str = "default") -> dict:
        """
        Record audio from microphone and transcribe speech.
        Falls back to file upload if streamlit-mic-recorder unavailable.
        
        Args:
            key_suffix: Unique key suffix for Streamlit component
        
        Returns:
            {
                "text": "transcribed text",
                "audio_path": "path/to/saved/audio.wav",
                "success": bool,
                "error": "error message if failed"
            }
        """
        try:
            # If streamlit-mic-recorder is available, use it for live recording
            if MIC_RECORDER_AVAILABLE:
                try:
                    st.info("🎤 **Press the button below to START recording, press again to STOP**")
                    
                    # Record audio using streamlit-mic-recorder
                    audio_data = mic_recorder(
                        start_prompt="🎤 Start Recording",
                        stop_prompt="⏹️ Stop Recording",
                        just_once=False,
                        use_container_width=True,
                        key=f"mic_recorder_{key_suffix}"
                    )
                    
                    if audio_data is not None and audio_data.get('bytes') is not None:
                        # Save audio file
                        audio_dir = "data/sessions"
                        os.makedirs(audio_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        audio_path = os.path.join(audio_dir, f"speech_{timestamp}.wav")
                        
                        # Get audio data
                        audio_bytes = audio_data['bytes']
                        
                        # Save to file
                        with open(audio_path, 'wb') as f:
                            f.write(audio_bytes)
                        
                        st.success(f"✓ Audio recorded: {os.path.basename(audio_path)}")
                        
                        # Transcribe using Whisper
                        return self.transcribe_audio_file(audio_path)
                    else:
                        return {
                            "text": "",
                            "audio_path": None,
                            "success": False,
                            "error": "No audio recorded"
                        }
                except Exception as e:
                    st.warning(f"⚠️ Microphone recording issue, using file upload instead")
                    # Fall through to file upload
            
            # Fallback to file upload
            st.info("📤 Upload an audio file (WAV, MP3, M4A, FLAC, OGG, OPUS, WEBM)")
            audio_file = st.file_uploader(
                "Choose audio file:",
                type=["wav", "mp3", "m4a", "flac", "ogg", "opus", "webm"],
                key=f"audio_fallback_{key_suffix}"
            )
            
            if audio_file:
                audio_dir = "data/sessions"
                os.makedirs(audio_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                audio_path = os.path.join(audio_dir, f"speech_{timestamp}_{audio_file.name}")
                
                with open(audio_path, "wb") as f:
                    f.write(audio_file.getbuffer())
                
                st.success(f"✓ Audio received: {audio_file.name}")
                return self.transcribe_audio_file(audio_path)
            
            return {
                "text": "",
                "audio_path": None,
                "success": False,
                "error": "No audio provided"
            }
        
        except Exception as e:
            st.error(f"Recording error: {str(e)}")
            return {
                "text": "",
                "audio_path": None,
                "success": False,
                "error": str(e)
            }
    
    def transcribe_audio_file(self, audio_path: str) -> dict:
        """
        Transcribe audio file using OpenAI Whisper API.
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            {
                "text": "transcribed text",
                "audio_path": audio_path,
                "success": bool,
                "error": error message if failed
            }
        """
        try:
            if not os.path.exists(audio_path):
                return {
                    "text": "",
                    "audio_path": audio_path,
                    "success": False,
                    "error": f"Audio file not found: {audio_path}"
                }
            
            # Show progress
            with st.spinner("🔄 Transcribing speech..."):
                with open(audio_path, 'rb') as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="en"
                    )
                
                transcribed_text = transcript.text.strip()
                
                if transcribed_text:
                    st.success(f"✓ Speech recognized: *{transcribed_text}*")
                else:
                    st.warning("⚠️ No speech detected. Please try again.")
                
                return {
                    "text": transcribed_text,
                    "audio_path": audio_path,
                    "success": bool(transcribed_text),
                    "error": None if transcribed_text else "No speech detected",
                    "mode": "voice"
                }
        
        except Exception as e:
            st.error(f"Transcription error: {str(e)}")
            return {
                "text": "",
                "audio_path": audio_path,
                "success": False,
                "error": str(e)
            }


class SimpleAudioInput:
    """Simple audio input with voice and text options."""
    
    def __init__(self):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai required")
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required")
        
        self.client = OpenAI(api_key=api_key)
        
        # Try to initialize recorder, but don't fail if it doesn't work
        try:
            self.recorder = StreamlitAudioRecorder()
        except Exception as e:
            st.warning(f"⚠️ Audio recording unavailable (will use file upload instead)")
            self.recorder = None
    
    def audio_input_ui(self, label: str = "Record or type your answer:",
                       key_suffix: str = "audio1") -> dict:
        """
        Audio input UI with voice and text options.
        
        Args:
            label: UI label
            key_suffix: Unique key suffix
        
        Returns:
            {
                "text": "answer text",
                "audio_path": "path/to/audio or None",
                "success": bool,
                "mode": "voice" or "text"
            }
        """
        st.write(f"**{label}**")
        
        # Create two tabs: Voice or Text
        tab1, tab2 = st.tabs(["🎤 Speak/Upload", "⌨️ Type"])
        
        with tab1:
            if self.recorder:
                # Use mic recorder if available
                result = self.recorder.record_and_transcribe(key_suffix=key_suffix)
                
                if result.get("success"):
                    return result
                elif result.get("error") and "No audio" not in result["error"]:
                    st.error(f"Error: {result.get('error')}")
            else:
                # Fallback: just file upload
                st.info("📤 Upload an audio file")
                audio_file = st.file_uploader(
                    "Choose audio file:",
                    type=["wav", "mp3", "m4a", "flac", "ogg", "opus", "webm"],
                    key=f"audio_upload_{key_suffix}"
                )
                
                if audio_file:
                    audio_dir = "data/sessions"
                    os.makedirs(audio_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    audio_path = os.path.join(audio_dir, f"speech_{timestamp}_{audio_file.name}")
                    
                    with open(audio_path, "wb") as f:
                        f.write(audio_file.getbuffer())
                    
                    st.success(f"✓ Audio received: {audio_file.name}")
                    return self.recorder.transcribe_audio_file(audio_path)
        
        with tab2:
            text_answer = st.text_area(
                "Type your answer here:",
                key=f"answer_text_{key_suffix}",
                height=100
            )
            
            if text_answer:
                return {
                    "text": text_answer,
                    "audio_path": None,
                    "success": True,
                    "error": None,
                    "mode": "text"
                }
        
        return {
            "text": "",
            "audio_path": None,
            "success": False,
            "error": "No answer provided",
            "mode": None
        }
