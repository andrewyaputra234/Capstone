# 🚀 Running the Streamlit Web UI

## Quick Start

### 1. Run the Streamlit App
```powershell
streamlit run app.py
```

The app will open at: **http://localhost:8501**

### 2. Features Available

#### Dashboard
- Overview of subjects, sessions, and rubrics
- Quick start instructions

#### Upload Document
- Upload PDF/DOCX/TXT files
- Configure subject name
- Select and map rubric
- Automatic processing and encoding

#### Assessment
- Select subject
- Enter student ID
- Interactive Q&A interface (coming soon - full integration)
- Real-time scoring

#### Results
- View all assessment sessions
- Browse Q&A history
- Export as CSV/JSON/Text
- Session analytics

#### Settings
- Manage rubrics
- Configure subject-to-rubric mapping
- View system information

---

## Features Implemented

✅ Dashboard with metrics
✅ Document upload & processing  
✅ Subject management
✅ Rubric configuration
✅ Session viewing
✅ Export functionality
✅ Settings management

---

## Next Steps

The assessment page currently has a simplified interface. To add full integration:

1. **Real-time Question Loading** - Load questions from DialogueManager
2. **Audio Recording** - Add microphone input support
3. **Live Feedback** - Show scores and feedback as questions are answered
4. **Session Tracking** - Full integration with SessionManager

---

## Troubleshooting

**Port already in use?**
```powershell
streamlit run app.py --server.port 8502
```

**Need to rebuild?**
```powershell
streamlit cache clear
```

**Check if packages are installed:**
```powershell
pip list | findstr streamlit
```
