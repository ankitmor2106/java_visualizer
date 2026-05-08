# Java Memory Visualizer

> Real-time JVM memory visualization powered by a custom Java Agent, JDI tracing, and an interactive full-stack IDE experience.

Java Memory Visualizer is a developer-focused educational tool that helps users understand how Java memory works internally.  
It compiles and executes Java code, traces JVM memory allocations in real time using the Java Debug Interface (JDI), and visualizes Stack ↔ Heap relationships through an interactive step-by-step interface.

Designed with a minimalist, IDE-inspired workflow and an Apple-style aesthetic.

---

## ✨ Features

### 🧠 Real-Time JVM Memory Tracing
- Custom Java Agent built with **JDI (Java Debug Interface)**
- Tracks:
  - Stack frames
  - Object allocations
  - References
  - Method calls
  - Variable state changes
- Emits structured JSON snapshots for visualization

### 🎯 Interactive Memory Visualization
- Dynamic Stack and Heap rendering
- Interactive SVG arrow system:
  - Maps references between variables and heap objects
  - Smooth visual connections
  - Real-time updates during step-through execution

### 💻 IDE-Like Workflow
Instead of a single execution button, the platform follows a structured 3-step workflow:

1. **Compile**
   - Runs `javac -g`
   - Locks editor to preserve execution consistency

2. **Run**
   - Executes compiled bytecode
   - Displays console output

3. **Visualize**
   - Opens modal-based memory playback
   - Step-through execution timeline

### ✍️ Monaco Editor Integration
- VS Code-like editing experience
- Syntax highlighting
- Java code input
- Lightweight and responsive UI

### 🐳 Dockerized Backend
- Includes:
  - Python 3.9
  - OpenJDK 17
- Fully containerized for reproducible deployment

---

# 🛠 Tech Stack

## Frontend
- HTML5
- CSS3
- Vanilla JavaScript
- Monaco Editor
- SVG Rendering

## Backend
- Python 3.9
- FastAPI
- subprocess-based execution pipeline

## JVM Tracing
- Java Agent
- Java Debug Interface (JDI)
- `javac -g`

## Deployment
- Docker
- Render

---

# 📁 Project Structure

```bash
java-memory-visualizer/
│
├── frontend/
│   ├── index.html
│   ├── styles/
│   ├── scripts/
│   ├── assets/
│   └── monaco/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routes/
│   │   ├── services/
│   │   └── tracer/
│   │
│   ├── agent/
│   │   ├── MemoryTracerAgent.java
│   │   └── JDIEventListener.java
│   │
│   ├── temp/
│   ├── Dockerfile
│   └── requirements.txt
│
├── README.md
└── docker-compose.yml
```

---

# 🚀 Local Setup

## Prerequisites

Install the following:

- Python 3.9+
- OpenJDK 17
- Docker (optional)

---

## 1. Clone the Repository

```bash
git clone https://github.com/your-username/java-memory-visualizer.git

cd java-memory-visualizer
```

---

## 2. Backend Setup

### Create Virtual Environment

```bash
cd backend

python -m venv venv
```

### Activate Environment

#### macOS / Linux

```bash
source venv/bin/activate
```

#### Windows

```bash
venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Start FastAPI Server

```bash
uvicorn app.main:app --reload
```

Backend runs on:

```bash
http://localhost:8000
```

---

## 3. Frontend Setup

Open the `frontend/` directory using any static server.

Example using VS Code Live Server:

```bash
frontend/index.html
```

Or using Python:

```bash
cd frontend

python -m http.server 5500
```

Frontend runs on:

```bash
http://localhost:5500
```

---

# ☕ Java Requirements

Ensure Java 17 is installed:

```bash
java -version
```

Expected output:

```bash
openjdk version "17"
```

The backend internally compiles code using:

```bash
javac -g
```

The `-g` flag preserves debugging metadata required for JDI memory tracing.

---

# 🐳 Docker Deployment

The backend is fully containerized with:

- Python 3.9
- OpenJDK 17
- FastAPI runtime

## Build Image

```bash
docker build -t java-memory-visualizer .
```

## Run Container

```bash
docker run -p 8000:8000 java-memory-visualizer
```

---

# ☁️ Render Deployment

Recommended deployment platform: **Render**

## Suggested Setup

### Backend
- Environment: Docker
- Root Directory: `/backend`
- Start Command handled by Docker

### Frontend
- Deploy as static site
- Publish directory: `/frontend`

---

# 🔍 How It Works

1. User writes Java code in Monaco Editor
2. Backend compiles code using `javac -g`
3. JVM launches with custom Java Agent
4. JDI captures runtime memory events
5. Events are streamed as structured JSON
6. Frontend renders:
   - Stack frames
   - Heap objects
   - SVG reference arrows
7. User steps through execution visually

---

# 🎯 Vision

Java Memory Visualizer aims to make JVM internals intuitive and observable.

Instead of reading static diagrams, developers can watch memory evolve in real time — making concepts like references, stack frames, object allocation, and method execution significantly easier to understand.

---


# 👨‍💻 Author - Ankitmor2106


Built for developers, students, and educators exploring JVM internals.
