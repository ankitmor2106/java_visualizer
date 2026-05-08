document.addEventListener('DOMContentLoaded', () => {
    // --- UI ELEMENTS ---
    const btnCompile = document.getElementById('btn-compile');
    const btnRun = document.getElementById('btn-run');
    const btnVisualize = document.getElementById('btn-visualize');
    
    const btnNext = document.getElementById('btn-next');
    const btnPrev = document.getElementById('btn-prev');
    const btnCloseModal = document.getElementById('btn-close-modal');
    
    const stepCounter = document.getElementById('step-counter');
    const stackContainer = document.getElementById('stack-container');
    const heapContainer = document.getElementById('heap-container');
    const consoleOutput = document.getElementById('console-output');
    const themeToggle = document.getElementById('theme-toggle');
    const visualizerModal = document.getElementById('visualizer-modal');

    // --- STATE ---
    let executionSteps = [];
    let fullStdout = "";
    let runtimeError = null;
    let currentStepIndex = 0;
    let editor;

    // --- DEFAULT CODE ---
    const defaultJavaCode = `class Record {
    int id;
    String status;
    public Record(int id, String status) { 
        this.id = id;
        this.status = status;
    }
}

class A {
    String name;

    A(String n) {
        name = n;
    }
}

public class Main {
    public static void main(String[] args) {

        A[] a = {
            new A("Ankit"),
            new A("Rahul"),
            new A("Aman"),
            new A("Priya"),
            new A("Sneha")
        };

        for (A x : a)
            System.out.println(x.name);
    }

}`;

    // --- INITIALIZE MONACO EDITOR ---
    require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' }});
    require(['vs/editor/editor.main'], function () {
        const savedTheme = localStorage.getItem('java-vis-theme') || 'dark';
        editor = monaco.editor.create(document.getElementById('editor-container'), {
            value: defaultJavaCode,
            language: 'java',
            theme: savedTheme === 'dark' ? 'vs-dark' : 'vs-light',
            automaticLayout: true,
            minimap: { enabled: false },
            fontSize: 15,
            padding: { top: 16 }
        });

        // Smart Lock: Disable Run/Visualize buttons if user modifies the code
        editor.onDidChangeModelContent(() => {
            if (!btnRun.disabled) {
                btnRun.disabled = true;
                btnVisualize.disabled = true;
                consoleOutput.textContent = "Code has been modified.\nPlease click 'Compile' to apply changes.";
            }
        });
    });

    // --- THEME LOGIC & CANVAS OPACITY ---
    let particlesColor = 'rgba(255, 255, 255, 0.7)'; 
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        themeToggle.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
        
        particlesColor = theme === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.4)';
        
        if(editor) monaco.editor.setTheme(theme === 'dark' ? 'vs-dark' : 'vs-light');
    }
    applyTheme(localStorage.getItem('java-vis-theme') || 'dark');
    themeToggle.addEventListener('click', () => {
        const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        localStorage.setItem('java-vis-theme', newTheme);
        applyTheme(newTheme);
    });

    // --- API & BUTTON LOGIC ---
    const API_ENDPOINT = 'https://java-visualizer-api.onrender.com/execute';

    // 1. COMPILE BUTTON
    btnCompile.addEventListener('click', async () => {
        const javaCode = editor.getValue();
        
        consoleOutput.textContent = "Compiling and analyzing code...";
        btnCompile.disabled = true;
        btnCompile.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><path d="M12 2v4"></path></svg> Processing...`;
        
        btnRun.disabled = true;
        btnVisualize.disabled = true;

        try {
            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: javaCode })
            });

            const backendData = await response.json();

            if (!response.ok || backendData.success === false) {
                let errorMsg = backendData.message || `Server Error: ${response.status}`;
                if (backendData.errors) {
                    errorMsg += "\n\n" + backendData.errors.map(e => `Line ${e.line}: ${e.message}`).join("\n");
                }
                throw new Error(errorMsg);
            }
            
            // Store data globally for the sub-buttons to use
            executionSteps = backendData.steps || [];
            runtimeError = backendData.runtimeError;
            
            // Extract the final cumulative output for the "Run" button
            fullStdout = executionSteps.length > 0 ? executionSteps[executionSteps.length - 1].stdout : "";
            
            consoleOutput.textContent = "Compilation Successful! ✅\n\nCode is ready.\n- Click 'Run' to see output.\n- Click 'Visualize' to trace memory.";
            
            // Unlock the smaller buttons
            btnRun.disabled = false;
            if (executionSteps.length > 0) {
                btnVisualize.disabled = false; 
            }

        } catch (error) {
            consoleOutput.textContent = `[COMPILATION ERROR]\n\nDetails: ${error.message}\n`;
            console.error("Backend Error:", error);
        } finally {
            btnCompile.disabled = false;
            btnCompile.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M12 2v4"></path><path d="M12 18v4"></path><path d="M4.93 4.93l2.83 2.83"></path><path d="M16.24 16.24l2.83 2.83"></path><path d="M2 12h4"></path><path d="M18 12h4"></path><path d="M4.93 19.07l2.83-2.83"></path><path d="M16.24 7.76l2.83-2.83"></path></svg> Compile`;
        }
    });

    // 2. RUN BUTTON (Shows terminal output instantly)
    btnRun.addEventListener('click', () => {
        let outputText = "--- Console Output ---\n";
        outputText += fullStdout || "(No output generated)";
        
        if (runtimeError) {
            outputText += `\n\n[RUNTIME EXCEPTION]:\n${runtimeError}`;
        }
        consoleOutput.textContent = outputText;
    });

    // 3. VISUALIZE BUTTON (Opens the Glass Modal)
    btnVisualize.addEventListener('click', () => {
        visualizerModal.classList.remove('hidden');
        document.body.classList.add('no-scroll'); 
        currentStepIndex = 0;
        updateUI();
    });

    // --- MODAL & RENDERING LOGIC ---
    btnCloseModal.addEventListener('click', () => {
        visualizerModal.classList.add('hidden');
        document.body.classList.remove('no-scroll'); 
    });

    btnNext.addEventListener('click', () => { if (currentStepIndex < executionSteps.length - 1) { currentStepIndex++; updateUI(); } });
    btnPrev.addEventListener('click', () => { if (currentStepIndex > 0) { currentStepIndex--; updateUI(); } });

    function updateUI() {
        if (executionSteps.length === 0) return;
        const currentState = executionSteps[currentStepIndex];

        btnPrev.disabled = currentStepIndex === 0;
        btnNext.disabled = currentStepIndex === executionSteps.length - 1;
        stepCounter.textContent = `Step: ${currentStepIndex + 1} / ${executionSteps.length}`;

        renderStack(currentState.stack);
        renderHeap(currentState.heap);
        setTimeout(drawArrows, 50); 
    }

    function renderStack(stackData) {
        stackContainer.innerHTML = '';
        
        for (const [methodName, variables] of Object.entries(stackData)) {
            stackContainer.innerHTML += `
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin: 10px 0 5px 5px; letter-spacing: 1px;">
                    Frame: ${methodName}()
                </div>`;

            for (const [varName, varString] of Object.entries(variables)) {
                const splitIndex = varString.indexOf(':');
                let type = varString;
                let val = "";
                let isRef = false;
                let targetId = "";
                
                if (splitIndex !== -1) {
                    type = varString.substring(0, splitIndex).trim();
                    val = varString.substring(splitIndex + 1).trim();
                }

                if (type === "ref") {
                    isRef = true;
                    targetId = val; 
                    val = "Object " + targetId.replace("obj_", "").replace("arr_", "").replace("box_", ""); 
                }

                const valClass = isRef ? `ref` : "val";
                const domId = `stack-${methodName}-${varName}`; 

                stackContainer.innerHTML += `
                    <div class="stack-row" id="${domId}">
                        <div><span class="type">${type}</span><span class="name">${varName}</span></div>
                        <span class="${valClass}" ${isRef ? `data-target="${targetId}" data-source="${domId}"` : ""}>${val}</span>
                    </div>
                `;
            }
        }
    }

    function renderHeap(heapData) {
        heapContainer.innerHTML = '';
        for (const [objId, objData] of Object.entries(heapData)) {
            let fieldsHtml = '';
            
            if (objData.fields) {
                for (const [key, val] of Object.entries(objData.fields)) {
                    fieldsHtml += `<div class="obj-row"><div class="obj-key">${key}</div><div class="obj-val">${val}</div></div>`;
                }
            } else if (objData.value) {
                fieldsHtml = `<div class="obj-row"><div class="obj-key" style="flex:0;">[ ]</div><div class="obj-val">${objData.value}</div></div>`;
            }

            const formattedId = objId.startsWith('obj_') ? 'Object ' + objId.substring(4) : objId;

            heapContainer.innerHTML += `
                <div class="heap-object" id="heap-${objId}">
                    <div class="obj-header">${objData.type} <span class="ref-id">@${formattedId}</span></div>
                    <div class="obj-body">${fieldsHtml}</div>
                </div>
            `;
        }
    }

    function drawArrows() {
        const svg = document.getElementById('arrow-svg');
        if (!svg) return;
        svg.querySelectorAll('path').forEach(p => p.remove());

        const pointers = document.querySelectorAll('.ref');
        const containerRect = document.getElementById('memory-grid').getBoundingClientRect();
        const stackRect = stackContainer.getBoundingClientRect();
        const heapRect = heapContainer.getBoundingClientRect();

        pointers.forEach(pointer => {
            const targetNode = document.getElementById(`heap-${pointer.getAttribute('data-target')}`);
            const sourceRow = document.getElementById(pointer.getAttribute('data-source'));
            
            if (targetNode && sourceRow) {
                const pRect = pointer.getBoundingClientRect();
                const tRect = targetNode.getBoundingClientRect();

                if (pRect.top < stackRect.top || pRect.bottom > stackRect.bottom) return;
                if (tRect.top < heapRect.top || tRect.bottom > heapRect.bottom) return;

                const startX = pRect.right - containerRect.left;
                const startY = pRect.top + pRect.height / 2 - containerRect.top;
                const endX = tRect.left - containerRect.left; 
                const endY = tRect.top + tRect.height / 2 - containerRect.top;

                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                const cp1X = startX + 100;
                const cp2X = endX - 100;
                
                path.setAttribute('d', `M ${startX} ${startY} C ${cp1X} ${startY}, ${cp2X} ${endY}, ${endX} ${endY}`);
                path.setAttribute('fill', 'none');
                path.setAttribute('stroke', 'var(--text-muted)');
                path.setAttribute('stroke-width', '2');
                path.setAttribute('stroke-opacity', '0.4'); 
                path.setAttribute('marker-end', 'url(#arrowhead)');
                svg.appendChild(path);

                const highlightConnection = () => {
                    path.setAttribute('stroke', 'var(--accent)');
                    path.setAttribute('stroke-width', '3');
                    path.setAttribute('stroke-opacity', '1');
                    path.setAttribute('marker-end', 'url(#arrowhead-highlight)');
                    targetNode.classList.add('highlighted');
                    sourceRow.classList.add('highlighted');
                };

                const removeHighlight = () => {
                    path.setAttribute('stroke', 'var(--text-muted)');
                    path.setAttribute('stroke-width', '2');
                    path.setAttribute('stroke-opacity', '0.4');
                    path.setAttribute('marker-end', 'url(#arrowhead)');
                    targetNode.classList.remove('highlighted');
                    sourceRow.classList.remove('highlighted');
                };

                pointer.addEventListener('mouseenter', highlightConnection);
                pointer.addEventListener('mouseleave', removeHighlight);
                targetNode.addEventListener('mouseenter', highlightConnection);
                targetNode.addEventListener('mouseleave', removeHighlight);
            }
        });
    }

    window.addEventListener('resize', () => { if(!visualizerModal.classList.contains('hidden')) drawArrows(); });
    stackContainer.addEventListener('scroll', drawArrows);
    heapContainer.addEventListener('scroll', drawArrows);

    // --- INTERACTIVE CANVAS BACKGROUND ---
    const canvas = document.getElementById('bg-canvas');
    const ctx = canvas.getContext('2d');
    let width, height, particles = [];

    function initCanvas() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
        particles = [];
        for(let i = 0; i < 70; i++) { 
            particles.push({ x: Math.random() * width, y: Math.random() * height, vx: (Math.random() - 0.5) * 0.5, vy: (Math.random() - 0.5) * 0.5 });
        }
    }

    function drawCanvas() {
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = particlesColor;
        ctx.strokeStyle = particlesColor;
        
        particles.forEach(p => {
            p.x += p.vx; p.y += p.vy;
            if(p.x < 0 || p.x > width) p.vx *= -1;
            if(p.y < 0 || p.y > height) p.vy *= -1;
            
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
            ctx.fill();
        });

        for(let i = 0; i < particles.length; i++) {
            for(let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if(dist < 150) {
                    ctx.globalAlpha = 1 - (dist / 150); 
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }
        ctx.globalAlpha = 1;
        requestAnimationFrame(drawCanvas);
    }
    window.addEventListener('resize', initCanvas);
    initCanvas();
    drawCanvas();
});
