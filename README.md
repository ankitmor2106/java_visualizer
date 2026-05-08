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
