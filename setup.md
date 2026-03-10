# GLM-OCR PDF Translation Project Setup

This guide will walk you through setting up both the FastAPI backend and the React frontend on your local machine. This project utilizes the local `zai-org/GLM-OCR` model for text extraction and Google Gemini for translation and reconstruction.

## Prerequisites
- **Python 3.10+** (Apple Silicon/M-series Mac recommended for MPS acceleration, but works on Windows CPU/CUDA as well)
- **Node.js 18+** & npm
- **Git**
- Your Google Gemini API Key

---

## 🍎 Setup for macOS (Apple Silicon / Intel)

We have provided an automated setup script for macOS.

### Automated Setup
1. Open your terminal and navigate to this project folder.
2. Make the script executable: `chmod +x setup_mac.sh`
3. Run the script: `./setup_mac.sh`
4. Update the `.env` files in both `backend` and `frontend` with your API keys.

### Manual Setup (macOS)

#### 1. Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Open .env and add your GEMINI_API_KEY
```

#### 2. Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env
# Open .env and configure your variables if needed
```

---

## 🪟 Setup for Windows

We have provided an automated setup script for Windows.

### Automated Setup
1. Open Command Prompt or PowerShell as Administrator and navigate to this project folder.
2. Run the batch script: `setup_windows.bat`
3. Update the `.env` files in both `backend` and `frontend` with your API keys.

### Manual Setup (Windows)

#### 1. Backend Setup
```cmd
cd backend
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
:: Open .env and add your GEMINI_API_KEY
```

#### 2. Frontend Setup
```cmd
cd frontend
npm install
copy .env.example .env
:: Open .env and configure your variables if needed
```

---

## 🚀 Running the Application

You must run both the backend and frontend servers simultaneously in separate terminal windows.

### 1. Start the Backend Server
**macOS:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
**Windows:**
```cmd
cd backend
venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start the Frontend Server
**Both macOS and Windows:**
```bash
cd frontend
npm run dev
```

The application will be available at `http://localhost:5174` (or the port specified by Vite in your terminal).

## Note on First Run
The first time you process an image, the backend will automatically download the `zai-org/GLM-OCR` huggingface model locally to your system cache. This model is roughly 2.65GB. Please ensure you have a stable internet connection for the first inference!
