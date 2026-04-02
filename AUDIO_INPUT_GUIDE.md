# Audio Recording & Speech-to-Text Integration (Phase 2.1)

## What's New

Your system now supports **audio input** from students during oral assessments!

### ✅ Completed Features

**New Agent Module:** `src/agent_audio_input.py`
- `AudioRecorder`: Record microphone audio to WAV files
- `SpeechToText`: Transcribe audio using OpenAI Whisper API

**Integrated with A3 (Dialogue Manager):**
- New method: `record_and_transcribe_answer()` - Records student voice and transcribes
- New CLI flag: `--use-audio-input` - Enable audio input mode
- Updated `interactive_assessment()` function

**Updated CLI (`run.py`):**
- New flag: `--use-audio-input` for dialogue command
- Full usage: `python run.py dialogue --interactive --subject math --use-audio-input`

## Requirements Implemented

| Requirement | Status | Details |
|---|---|---|
| **FR-4** (Audio Recording) | ✅ COMPLETE | Record via microphone, save WAV format |
| **FR-5** (Speech-to-Text) | ✅ COMPLETE | Transcribe using OpenAI Whisper API |
| **FR-6** (Storage) | ✅ COMPLETE | Save audio + transcriptions in `data/sessions/` |

## Usage

### 1. Standalone Audio Recording

```bash
# Record 10 seconds of audio
python src/agent_audio_input.py record --duration 10

# Save to specific location
python src/agent_audio_input.py record --duration 15 --output "audio.wav"
```

### 2. Standalone Transcription

```bash
# Transcribe existing audio file
python src/agent_audio_input.py transcribe --audio "audio.wav"

# Save transcription to JSON
python src/agent_audio_input.py transcribe --audio "audio.wav" --output "transcription.json"
```

### 3. Interactive Session (Record + Transcribe)

```bash
# Single session with recording + transcription
python src/agent_audio_input.py session --duration 15 --session-id "session_001"

# Files saved to: data/sessions/session_001/
#   └── audio.wav
#   └── transcription.json
```

### 4. Dialogue Assessment with Audio Input

```bash
# Text input (original)
python run.py dialogue --interactive --subject math --rubric primary1_math

# Audio input (NEW)
python run.py dialogue --interactive --subject math --rubric primary1_math --use-audio-input

# With both audio output AND audio input
python run.py dialogue --interactive --subject math --rubric primary1_math --audio --use-audio-input
```

### 5. Programmatic Usage

```python
from src.agent_audio_input import AudioRecorder, SpeechToText

# Record audio
recorder = AudioRecorder()
audio_path = recorder.record_audio(duration=15, output_path="student_answer.wav")

# Transcribe
stt = SpeechToText()
result = stt.transcribe_audio("student_answer.wav")
print(f"Transcription: {result['text']}")
print(f"Confidence: {result['confidence']}")  # None - Whisper doesn't provide this

# Or transcribe and save
text = stt.transcribe_file("student_answer.wav", output_path="transcription.json")
```

## Output Structure

### Session Files
```
data/sessions/
├── q1_answer.wav              # Student answer audio for Q1
├── q1_transcription.json      # Transcription of Q1 answer
├── q2_answer.wav              # Student answer audio for Q2
├── q2_transcription.json      # Transcription of Q2 answer
└── ...
```

### Transcription JSON Format
```json
{
  "question_id": 1,
  "audio_file": "data/sessions/q1_answer.wav",
  "transcription": {
    "text": "The mitochondria is the powerhouse of the cell...",
    "duration": null,
    "confidence": null,
    "model": "whisper-1"
  }
}
```

## System Behavior

### When `--use-audio-input` Enabled

For each question:

1. **Question Display**
   ```
   ❓ Question 1/3:
   Explain the photosynthesis process.
   ```

2. **Recording Prompt**
   ```
   🎤 Recording audio answer (15 seconds max)...
   Recording for 15 seconds...
   Press Ctrl+C to stop early.
   
   Recording... 1s / 15s
   Recording... 2s / 15s
   ...
   ```

3. **Audio Save**
   ```
   ✓ Audio saved: data/sessions/q1_answer.wav (0.25 MB)
   ```

4. **Transcription**
   ```
   🔄 Transcribing audio: q1_answer.wav
   ✓ Transcribed: The mitochondria is the powerhouse of the cell and performs cellular respiration...
   ```

5. **Response Display**
   ```
   ✓ Transcribed answer: The mitochondria is the powerhouse of the cell...
   ```

6. **Evaluation** (as before)
   ```
   ⏳ Evaluating answer...
   📊 Scores by Criterion:
     Clarity: 4/5
     Content: 5/5
   Total: 9/10 (90%)
   ```

## API Keys Required

**OPENAI_API_KEY** - For Whisper transcription
- Already required for gpt-3.5-turbo (LLM)
- Whisper is very cheap: ~$0.02 per minute of audio

## Error Handling

### If PyAudio Not Installed
```
⚠️ Audio module not available. Please install: pip install pyaudio openai
```

### If Recording Fails
```
❌ Failed to record/transcribe audio. Try again.
```

### If Transcription Fails
```
❌ Audio recording/transcription error: [error details]
```

## Performance Metrics

| Operation | Time | Cost |
|---|---|---|
| Record 15s audio | ~15s (real-time) | $0.00 |
| Transcribe 15s audio | ~3-5s (API latency) | ~$0.005 |
| Total per question | ~20s | ~$0.005 |

For 10 questions: ~3 minutes, ~$0.05 in API costs

## Requirements Met

✅ **FR-4:** Record audio via microphone  
✅ **FR-5:** Transcribe using OpenAI Whisper API  
✅ **FR-6:** Store audio files and transcriptions  

## Testing Checklist

- [ ] Test basic audio recording: `python src/agent_audio_input.py record`
- [ ] Test transcription: `python src/agent_audio_input.py transcribe --audio test.wav`
- [ ] Test dialogue with audio input: `python run.py dialogue --interactive --use-audio-input`
- [ ] Verify audio files saved in `data/sessions/`
- [ ] Verify transcriptions accurate and saved as JSON
- [ ] Verify scores computed correctly from transcribed text
- [ ] Test with multiple questions (check turn numbering)

## Next Phase: Session Management (FR-1 to FR-3)

With audio input complete, the remaining critical features are:

1. **Session Manager (A6)** - Create sessions with unique IDs
2. **Transcript Logging** - Structured turn-by-turn logs
3. **Export Functionality** - Save transcripts as JSON/CSV/DOCX

Progress: **3/5 phases complete** (60%)
