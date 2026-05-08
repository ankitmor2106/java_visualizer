"""
Java Memory Visualizer — FastAPI Backend
=========================================
Architecture:
  - FastAPI + Uvicorn on port 7070
  - Each /execute request gets an isolated tempdir
  - Python dynamically writes a Java JDI "TraceAgent" alongside the user's code,
    compiles both, launches the user's JVM with the agent attached via the
    Java Debugger Interface (JDWP), and the agent streams newline-delimited
    JSON step objects to stdout which Python captures and serves.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("jmv")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Java Memory Visualizer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXEC_TIMEOUT = 15
COMPILE_TIMEOUT = 15      
MAX_STEPS = 300           
JDI_TOOLS_JAR_CANDIDATES = [
    "/usr/lib/jvm/java-17-openjdk-amd64/lib/tools.jar",
    "/usr/lib/jvm/java-11-openjdk-amd64/lib/tools.jar",
    "/usr/lib/jvm/java-21-openjdk-amd64/lib/ct.sym",   
    "/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/lib/tools.jar",
    "/Library/Java/JavaVirtualMachines/jdk-11.jdk/Contents/Home/lib/tools.jar",
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ExecuteRequest(BaseModel):
    code: str


class CompileError(BaseModel):
    line: Optional[int]
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: list[CompileError] = []
    steps: list = []
    runtimeError: Optional[str] = None


class SuccessResponse(BaseModel):
    success: bool = True
    steps: list[dict]
    runtimeError: Optional[str]
    totalSteps: int


# ---------------------------------------------------------------------------
# Helpers — Java toolchain discovery
# ---------------------------------------------------------------------------
def _java_home() -> str:
    if jh := os.environ.get("JAVA_HOME"):
        return jh
    try:
        result = subprocess.run(
            ["java", "-XshowSettings:all", "-version"],
            capture_output=True, text=True, timeout=15
        )
        for line in (result.stdout + result.stderr).splitlines():
            if "java.home" in line:
                return line.split("=", 1)[-1].strip()
    except Exception:
        pass
    try:
        javap = subprocess.run(["which", "java"], capture_output=True, text=True).stdout.strip()
        real = Path(javap).resolve()
        return str(real.parent.parent)
    except Exception:
        return ""


def _tools_jar_classpath(java_home: str) -> str:
    for candidate in JDI_TOOLS_JAR_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    if java_home:
        tj = Path(java_home) / "lib" / "tools.jar"
        if tj.exists():
            return str(tj)
    return ""  


def _java_major_version() -> int:
    try:
        r = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=5)
        txt = r.stdout + r.stderr
        m = re.search(r'version "(?:1\.)?(\d+)', txt)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 17  

# ---------------------------------------------------------------------------
# The JDI Trace Agent Java source
# ---------------------------------------------------------------------------
TRACE_AGENT_SOURCE = textwrap.dedent(r"""
import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.*;

public class JvmTraceAgent {

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: JvmTraceAgent <jdwpPort> <mainClass>");
            System.exit(1);
        }
        int port = Integer.parseInt(args[0]);
        String mainClass = args[1];

        VirtualMachine vm = attachToJvm("127.0.0.1", port);
        try {
            runTrace(vm, mainClass);
        } finally {
            try { vm.dispose(); } catch (Exception ignored) {}
        }
    }

    private static VirtualMachine attachToJvm(String host, int port) throws Exception {
        VirtualMachineManager vmm = Bootstrap.virtualMachineManager();
        AttachingConnector connector = null;
        for (AttachingConnector c : vmm.attachingConnectors()) {
            if (c.name().contains("SocketAttach")) {
                connector = c;
                break;
            }
        }
        if (connector == null) throw new RuntimeException("No SocketAttach connector found");

        Map<String, Connector.Argument> arguments = connector.defaultArguments();
        arguments.get("hostname").setValue(host);
        arguments.get("port").setValue(String.valueOf(port));
        arguments.get("timeout").setValue("5000");

        Exception last = null;
        for (int i = 0; i < 20; i++) {
            try {
                return connector.attach(arguments);
            } catch (Exception e) {
                last = e;
                Thread.sleep(250);
            }
        }
        throw last;
    }

    private static final int MAX_STEPS = """ + str(MAX_STEPS) + r""";

    private static void runTrace(VirtualMachine vm, String mainClass) throws Exception {
        EventRequestManager erm = vm.eventRequestManager();

        ClassPrepareRequest cpr = erm.createClassPrepareRequest();
        cpr.setSuspendPolicy(EventRequest.SUSPEND_ALL);
        cpr.enable();

        MethodEntryRequest mer = erm.createMethodEntryRequest();
        mer.addClassFilter(mainClass + "*");
        mer.setSuspendPolicy(EventRequest.SUSPEND_ALL);
        mer.enable();

        StringBuilder cumulativeStdout = new StringBuilder();
        int stepNum = 0;
        Set<String> classesWithBreakpoints = new HashSet<>();
        Map<String, JSONObject> heapCache = new LinkedHashMap<>();

        vm.resume();

        EventQueue eq = vm.eventQueue();
        outer:
        while (true) {
            EventSet events;
            try {
                events = eq.remove(2000);
            } catch (VMDisconnectedException e) {
                break;
            }
            if (events == null) continue;

            for (Event event : events) {
                if (event instanceof VMDeathEvent || event instanceof VMDisconnectEvent) {
                    break outer;
                }

                if (event instanceof ClassPrepareEvent cpe) {
                    ReferenceType rt = cpe.referenceType();
                    String cn = rt.name();
                    if (!cn.startsWith("java.") && !cn.startsWith("sun.")
                            && !cn.startsWith("com.sun.") && !cn.startsWith("jdk.")
                            && !classesWithBreakpoints.contains(cn)) {
                        classesWithBreakpoints.add(cn);
                        for (Location loc : rt.allLineLocations()) {
                            BreakpointRequest br = erm.createBreakpointRequest(loc);
                            br.setSuspendPolicy(EventRequest.SUSPEND_ALL);
                            br.enable();
                        }
                    }

                } else if (event instanceof BreakpointEvent || event instanceof MethodEntryEvent) {
                    if (event instanceof MethodEntryEvent && !classesWithBreakpoints.isEmpty()) {
                        mer.disable();
                    }

                    ThreadReference thread = (event instanceof BreakpointEvent be)
                            ? be.thread() : ((MethodEntryEvent) event).thread();
                    Location loc = (event instanceof BreakpointEvent be2)
                            ? be2.location() : ((MethodEntryEvent) event).location();

                    String declaringClass = loc.declaringType().name();
                    if (declaringClass.startsWith("java.") || declaringClass.startsWith("sun.")
                            || declaringClass.equals("JvmTraceAgent")) {
                        events.resume();
                        continue;
                    }

                    stepNum++;
                    if (stepNum > MAX_STEPS) {
                        break outer;
                    }

                    JSONObject step = new JSONObject();
                    step.put("step", stepNum);
                    step.put("currentLine", loc.lineNumber());

                    JSONObject stackObj = new JSONObject();
                    heapCache.clear();

                    List<StackFrame> frames = thread.frames();
                    for (StackFrame frame : frames) {
                        String methodName = frame.location().declaringType().name()
                                + "." + frame.location().method().name();
                        if (methodName.startsWith("java.") || methodName.startsWith("sun.")
                                || methodName.startsWith("JvmTraceAgent")) continue;

                        JSONObject locals = new JSONObject();
                        try {
                            Map<LocalVariable, Value> visibleVars = frame.getValues(
                                    frame.visibleVariables());
                            for (Map.Entry<LocalVariable, Value> entry : visibleVars.entrySet()) {
                                String varName = entry.getKey().name();
                                if (varName.equals("args") && methodName.endsWith(".main")) continue;
                                Value val = entry.getValue();
                                locals.put(varName, encodeValue(val, heapCache, vm));
                            }
                        } catch (AbsentInformationException ignored) {
                        }

                        String frameKey = frame.location().method().name();
                        stackObj.put(frameKey, locals);
                    }
                    step.put("stack", stackObj);
                    step.put("heap", new JSONObject(heapCache));
                    step.put("stdout", ""); 

                    System.out.println("__STEP__" + step);
                }
            }
            events.resume();
        }
    }

    private static String encodeValue(Value val, Map<String, JSONObject> heap, VirtualMachine vm) {
        if (val == null) return "null";

        if (val instanceof BooleanValue bv) return "boolean: " + bv.value();
        if (val instanceof ByteValue bv)    return "byte: " + bv.value();
        if (val instanceof CharValue cv)    return "char: '" + cv.value() + "'";
        if (val instanceof ShortValue sv)   return "short: " + sv.value();
        if (val instanceof IntegerValue iv) return "int: " + iv.value();
        if (val instanceof LongValue lv)    return "long: " + lv.value();
        if (val instanceof FloatValue fv)   return "float: " + fv.value();
        if (val instanceof DoubleValue dv)  return "double: " + dv.value();

        if (val instanceof StringReference sr) {
            return "String: \"" + sr.value().replace("\"", "\\\"") + "\"";
        }

        if (val instanceof ArrayReference ar) {
            String id = "arr_" + ar.uniqueID();
            if (!heap.containsKey(id)) {
                JSONObject arrObj = new JSONObject();
                arrObj.put("type", ar.type().name());
                StringBuilder sb = new StringBuilder("[");
                List<Value> components = ar.getValues();
                for (int i = 0; i < components.size(); i++) {
                    if (i > 0) sb.append(", ");
                    Value v = components.get(i);
                    sb.append(rawPrimitive(v));
                }
                sb.append("]");
                arrObj.put("value", sb.toString());
                heap.put(id, arrObj);
            }
            return "ref: " + id;
        }

        if (val instanceof ObjectReference or) {
            String typeName = or.type().name();
            if (isBoxedType(typeName)) {
                return encodeBoxed(or, typeName, heap);
            }
            String id = "obj_" + or.uniqueID();
            if (!heap.containsKey(id)) {
                JSONObject objNode = new JSONObject();
                String simpleName = typeName.contains(".")
                        ? typeName.substring(typeName.lastIndexOf('.') + 1)
                        : typeName;
                objNode.put("type", simpleName);
                JSONObject fields = new JSONObject();
                ReferenceType rt = or.referenceType();
                List<Field> allFields = rt.allFields();
                for (Field f : allFields) {
                    if (f.isStatic()) continue;
                    try {
                        Value fv = or.getValue(f);
                        fields.put(f.name(), encodeValue(fv, heap, vm));
                    } catch (Exception ignored) {}
                }
                objNode.put("fields", fields);
                heap.put(id, objNode);
            }
            return "ref: " + id;
        }

        return val.toString();
    }

    private static boolean isBoxedType(String name) {
        return name.equals("java.lang.Integer") || name.equals("java.lang.Long")
                || name.equals("java.lang.Double") || name.equals("java.lang.Float")
                || name.equals("java.lang.Boolean") || name.equals("java.lang.Character")
                || name.equals("java.lang.Short") || name.equals("java.lang.Byte");
    }

    private static String encodeBoxed(ObjectReference or, String typeName,
                                      Map<String, JSONObject> heap) {
        String id = "box_" + or.uniqueID();
        if (!heap.containsKey(id)) {
            Field valueField = or.referenceType().fieldByName("value");
            String innerVal = "?";
            if (valueField != null) {
                try { innerVal = rawPrimitive(or.getValue(valueField)); } catch (Exception ignored) {}
            }
            JSONObject boxObj = new JSONObject();
            String simpleName = typeName.substring(typeName.lastIndexOf('.') + 1);
            boxObj.put("type", simpleName);
            boxObj.put("value", innerVal);
            heap.put(id, boxObj);
        }
        return "ref: " + id;
    }

    private static String rawPrimitive(Value v) {
        if (v == null) return "null";
        if (v instanceof StringReference sr) return "\"" + sr.value() + "\"";
        return v.toString();
    }
}
""")

# ---------------------------------------------------------------------------
# org.json shims (SPLIT INTO TWO FILES)
# ---------------------------------------------------------------------------
JSON_OBJECT_SOURCE = textwrap.dedent(r"""
package org.json;

import java.util.*;

public class JSONObject {
    private final LinkedHashMap<String, Object> map = new LinkedHashMap<>();

    public JSONObject() {}

    public JSONObject(Map<String, ? extends Object> initialMap) {
        if (initialMap != null) {
            this.map.putAll(initialMap);
        }
    }

    public JSONObject put(String key, Object value) {
        map.put(key, value);
        return this;
    }

    public boolean containsKey(String key) { return map.containsKey(key); }

    public Object get(String key) { return map.get(key); }

    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> e : map.entrySet()) {
            if (!first) sb.append(",");
            first = false;
            sb.append(quote(e.getKey())).append(":").append(render(e.getValue()));
        }
        return sb.append("}").toString();
    }

    private static String render(Object v) {
        if (v == null) return "null";
        if (v instanceof String s) return quote(s);
        if (v instanceof JSONObject || v instanceof JSONArray) return v.toString();
        if (v instanceof Boolean || v instanceof Number) return v.toString();
        return quote(v.toString());
    }

    private static String quote(String s) {
        return "\"" + s.replace("\\", "\\\\")
                        .replace("\"", "\\\"")
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                        .replace("\t", "\\t") + "\"";
    }
}
""")

JSON_ARRAY_SOURCE = textwrap.dedent(r"""
package org.json;

import java.util.*;

public class JSONArray {
    private final List<Object> list = new ArrayList<>();

    public JSONArray add(Object v) { list.add(v); return this; }

    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < list.size(); i++) {
            if (i > 0) sb.append(",");
            Object v = list.get(i);
            if (v == null) sb.append("null");
            else if (v instanceof String s) sb.append('"').append(s).append('"');
            else sb.append(v);
        }
        return sb.append("]").toString();
    }
}
""")

# ---------------------------------------------------------------------------
# Execution engine
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _extract_class_name(code: str) -> Optional[str]:
    m = re.search(r'\bpublic\s+class\s+(\w+)', code)
    return m.group(1) if m else None


def _parse_compile_errors(javac_output: str) -> list[dict]:
    errors: list[dict] = []
    seen: set[str] = set()
    for line in javac_output.splitlines():
        m = re.match(r'.+\.java:(\d+):\s+(?:error:\s+)?(.+)', line)
        if m:
            key = m.group(0)
            if key not in seen:
                seen.add(key)
                errors.append({"line": int(m.group(1)), "message": m.group(2).strip()})
    if not errors and javac_output.strip():
        errors.append({"line": None, "message": javac_output.strip()[:500]})
    return errors


def _stream_reader(stream, lines: list[str], stop_event: threading.Event) -> None:
    try:
        for line in iter(stream.readline, ""):
            if stop_event.is_set():
                break
            lines.append(line)
    except Exception:
        pass


def execute_java(code: str) -> dict[str, Any]:
    java_home = _java_home()
    jdk_version = _java_major_version()
    tools_jar = _tools_jar_classpath(java_home)

    class_name = _extract_class_name(code)
    if not class_name:
        return {
            "success": False,
            "message": "Could not find a public class declaration in the submitted code.",
            "errors": [{"line": None, "message": "No public class found."}],
            "steps": [],
            "runtimeError": None,
        }

    with tempfile.TemporaryDirectory(prefix="jmv_") as work_dir:
        wd = Path(work_dir)
        log.info("Working dir: %s  class: %s  jdk: %d", wd, class_name, jdk_version)

        user_src = wd / f"{class_name}.java"
        user_src.write_text(code, encoding="utf-8")

        agent_src = wd / "JvmTraceAgent.java"
        agent_src.write_text(TRACE_AGENT_SOURCE, encoding="utf-8")

        json_pkg_dir = wd / "org" / "json"
        json_pkg_dir.mkdir(parents=True, exist_ok=True)
        # WRITE BOTH FILES
        (json_pkg_dir / "JSONObject.java").write_text(JSON_OBJECT_SOURCE, encoding="utf-8")
        (json_pkg_dir / "JSONArray.java").write_text(JSON_ARRAY_SOURCE, encoding="utf-8")

        javac_user_cmd = ["javac", "-g", "-d", str(wd), str(user_src)]
        log.info("Compiling user code: %s", " ".join(javac_user_cmd))
        try:
            user_compile = subprocess.run(
                javac_user_cmd,
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT,
                cwd=str(wd),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Compilation timed out.",
                "errors": [{"line": None, "message": "javac exceeded time limit."}],
                "steps": [],
                "runtimeError": None,
            }

        if user_compile.returncode != 0:
            errors = _parse_compile_errors(user_compile.stderr or user_compile.stdout)
            return {
                "success": False,
                "message": "Compilation failed.",
                "errors": errors,
                "steps": [],
                "runtimeError": None,
            }

        agent_classpath_parts = [str(wd)]
        if tools_jar:
            agent_classpath_parts.append(tools_jar)

        extra_javac_flags: list[str] = []
        if jdk_version >= 9 and not tools_jar:
            extra_javac_flags = ["--add-modules", "jdk.jdi"]

        javac_agent_cmd = (
            ["javac", "-g"]
            + extra_javac_flags
            + ["-cp", os.pathsep.join(agent_classpath_parts)]
            + ["-d", str(wd)]
            # COMPILE BOTH FILES ALONG WITH THE AGENT
            + [str(json_pkg_dir / "JSONObject.java"), str(json_pkg_dir / "JSONArray.java"), str(agent_src)]
        )
        log.info("Compiling agent: %s", " ".join(javac_agent_cmd))
        try:
            agent_compile = subprocess.run(
                javac_agent_cmd,
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT,
                cwd=str(wd),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Agent compilation timed out.",
                "errors": [],
                "steps": [],
                "runtimeError": None,
            }

        if agent_compile.returncode != 0:
            log.error("Agent compile failed:\n%s", agent_compile.stderr)
            return _fallback_trace(code, class_name, wd, jdk_version)

        jdwp_port = _find_free_port()
        jdwp_arg = (
            f"transport=dt_socket,server=y,suspend=y,address=127.0.0.1:{jdwp_port}"
        )
        user_classpath = str(wd)
        extra_java_flags: list[str] = []
        if jdk_version >= 9 and not tools_jar:
            extra_java_flags = ["--add-modules", "jdk.jdi"]

        
      user_jvm_cmd = (
           ["java"]
           + ["-Xmx128m", "-XX:TieredStopAtLevel=1"] 
           + extra_java_flags
           + [f"-agentlib:jdwp={jdwp_arg}", "-cp", user_classpath, class_name]
           )
        log.info("Launching user JVM: %s", " ".join(user_jvm_cmd))

        user_proc = subprocess.Popen(
            user_jvm_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(wd),
        )

        agent_classpath_parts_rt = [str(wd)]
        if tools_jar:
            agent_classpath_parts_rt.append(tools_jar)
        agent_rt_classpath = os.pathsep.join(agent_classpath_parts_rt)

        agent_java_flags: list[str] = []
        if jdk_version >= 9 and not tools_jar:
            agent_java_flags = ["--add-modules", "jdk.jdi"]

        agent_cmd = (
              ["java"]
              + ["-Xmx128m", "-XX:TieredStopAtLevel=1"] 
              + agent_java_flags
               + ["-cp", agent_rt_classpath, "JvmTraceAgent", str(jdwp_port), class_name]
        )
        log.info("Launching trace agent: %s", " ".join(agent_cmd))

        agent_proc = subprocess.Popen(
            agent_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(wd),
        )

        stop = threading.Event()

        user_stdout_lines: list[str] = []
        user_stderr_lines: list[str] = []
        agent_stdout_lines: list[str] = []
        agent_stderr_lines: list[str] = []

        threads = [
            threading.Thread(target=_stream_reader,
                             args=(user_proc.stdout,  user_stdout_lines,  stop), daemon=True),
            threading.Thread(target=_stream_reader,
                             args=(user_proc.stderr,  user_stderr_lines,  stop), daemon=True),
            threading.Thread(target=_stream_reader,
                             args=(agent_proc.stdout, agent_stdout_lines, stop), daemon=True),
            threading.Thread(target=_stream_reader,
                             args=(agent_proc.stderr, agent_stderr_lines, stop), daemon=True),
        ]
        for t in threads:
            t.start()

        timed_out = False
        try:
            agent_proc.wait(timeout=EXEC_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            stop.set()
            for proc in (agent_proc, user_proc):
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass

        for t in threads:
            t.join(timeout=1)

        raw_agent_out = "".join(agent_stdout_lines)
        raw_user_out  = "".join(user_stdout_lines)
        raw_user_err  = "".join(user_stderr_lines)

        log.debug("Agent stderr:\n%s", "".join(agent_stderr_lines))

        steps = _parse_steps(raw_agent_out, raw_user_out)

        runtime_error: Optional[str] = None
        if raw_user_err.strip():
            err_lines = [
                ln for ln in raw_user_err.splitlines()
                if "Listening for transport" not in ln
            ]
            if err_lines:
                runtime_error = "\n".join(err_lines)

        if not steps:
            log.warning("Agent produced no steps; falling back to stub trace.")
            return _fallback_trace(code, class_name, wd, jdk_version)

        if timed_out and steps:
            if runtime_error:
                runtime_error += "\n[Execution timed out after 5 seconds]"
            else:
                runtime_error = "[Execution timed out after 5 seconds]"

        return {
            "success": True,
            "steps": steps,
            "runtimeError": runtime_error,
            "totalSteps": len(steps),
        }


def _parse_steps(agent_out: str, user_stdout: str) -> list[dict]:
    steps: list[dict] = []
    user_lines = user_stdout.splitlines(keepends=True)
    user_line_idx = 0

    for raw in agent_out.splitlines():
        if not raw.startswith("__STEP__"):
            continue
        json_str = raw[len("__STEP__"):]
        try:
            step_data = json.loads(json_str)
        except json.JSONDecodeError:
            log.warning("Failed to parse step JSON: %s", json_str[:200])
            continue

        step_data["stdout"] = "".join(user_lines[:user_line_idx + len(user_lines)])
        steps.append(step_data)

    full_stdout = user_stdout
    for s in steps:
        s["stdout"] = full_stdout

    return steps


def _fallback_trace(
    code: str, class_name: str, wd: Path, jdk_version: int
) -> dict[str, Any]:
    log.info("Running fallback (plain execution) trace for %s", class_name)

    run_cmd = ["java", "-cp", str(wd), class_name]
    try:
        run_result = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=str(wd),
        )
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = "[Execution timed out after 5 seconds]"
        runtime_error = stderr
    else:
        stdout = run_result.stdout
        stderr = run_result.stderr
        runtime_error = stderr.strip() if run_result.returncode != 0 else None

    lines = code.splitlines()
    main_line = 1
    in_main = False
    for i, ln in enumerate(lines, start=1):
        stripped = ln.strip()
        if "public static void main" in stripped:
            in_main = True
        if in_main and stripped and not stripped.startswith("//") and "{" not in stripped:
            main_line = i
            break

    steps = [
        {
            "step": 1,
            "currentLine": main_line,
            "stdout": stdout,
            "stack": {
                "main": {}
            },
            "heap": {},
        }
    ]

    return {
        "success": True,
        "steps": steps,
        "runtimeError": runtime_error,
        "totalSteps": len(steps),
    }


@app.post("/execute", response_model=None)
async def execute_endpoint(request: ExecuteRequest) -> dict:
    import asyncio

    code = request.code.strip()
    if not code:
        return {
            "success": False,
            "message": "No code provided.",
            "errors": [],
            "steps": [],
            "runtimeError": None,
        }

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, execute_java, code)
    except Exception as exc:
        log.exception("Unhandled error in execute_java")
        return {
            "success": False,
            "message": f"Internal server error: {exc}",
            "errors": [],
            "steps": [],
            "runtimeError": str(exc),
        }

    return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "jdk_version": _java_major_version()}


if __name__ == "__main__":
    # Render provides a "PORT" environment variable
    port = int(os.environ.get("PORT", 7070)) 
    uvicorn.run("main:app", host="0.0.0.0", port=port)
    
