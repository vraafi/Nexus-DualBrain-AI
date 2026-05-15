from flask import Flask, render_template_string, jsonify, request
import sqlite3
import os
import psutil

app = Flask(__name__)
DB_NAME = "agent_state.db"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AGI-Lite Command Center</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px; }
        .container { max-width: 800px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #333; }
        .section { margin-bottom: 20px; }
        .data-card { background: #eef; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
        .highlight { font-weight: bold; color: #0066cc; }
    </style>
    <script>
        async function fetchData() {
            const response = await fetch('/api/data');
            const data = await response.json();

            document.getElementById('cpu').innerText = data.hardware.cpu + "%";
            document.getElementById('ram').innerText = data.hardware.ram + "%";

            document.getElementById('revenue').innerText = "$" + data.finance.revenue;
            document.getElementById('jobs').innerText = data.finance.completed_jobs;

            const taskList = document.getElementById('tasks');
            taskList.innerHTML = "";
            data.tasks.forEach(task => {
                taskList.innerHTML += `<div class="data-card">[${task[1]}] ${task[0].substring(0,8)}... -> <span class="highlight">${task[2]}</span></div>`;
            });
        }
        setInterval(fetchData, 2000);
        window.onload = fetchData;
    </script>
</head>
<body>
    <div class="container">
        <h1>AGI-Lite Command Center</h1>

        <div class="section">
            <h2>Hardware Monitor</h2>
            <div class="data-card">CPU: <span id="cpu" class="highlight"></span> | RAM: <span id="ram" class="highlight"></span></div>
        </div>

        <div class="section">
            <h2>Financial Summary</h2>
            <div class="data-card">Delivered Jobs: <span id="jobs" class="highlight"></span> | Total Revenue: <span id="revenue" class="highlight"></span></div>
        </div>

        <div class="section">
            <h2>Active Tasks</h2>
            <div id="tasks"></div>
        </div>
    </div>
</body>
</html>
"""

def get_hardware_stats():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent()
    return {"cpu": cpu, "ram": ram.percent}

def get_active_tasks():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, status, current_step FROM task_state ORDER BY id DESC LIMIT 5")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception:
        return []

def get_financial_stats():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='finance_log'")
        if cursor.fetchone()[0] == 1:
            cursor.execute('SELECT COUNT(*), SUM(actual_revenue) FROM finance_log WHERE status = "DELIVERED" OR status = "PAID"')
            row = cursor.fetchone()
            completed = row[0] if row[0] else 0
            revenue = row[1] if row[1] else 0.0
            conn.close()
            return {"completed_jobs": completed, "revenue": f"{revenue:.2f}"}
    except Exception:
        pass
    return {"completed_jobs": 0, "revenue": "0.00"}

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def api_data():
    return jsonify({
        "hardware": get_hardware_stats(),
        "tasks": get_active_tasks(),
        "finance": get_financial_stats()
    })


# --- CashClaw Integration Endpoints ---
# These endpoints act as the bridge between CashClaw's Node.js brain and Nexus DualBrain's Python browser automation.

@app.route('/api/inbox', methods=['GET'])
def cashclaw_inbox():
    # Return empty for now as placeholder to allow CashClaw to start without errors
    # In full implementation, this would instantiate BrowserAgent and call FreelanceAgent.scrape_jobs()
    return jsonify({"tasks": []})

@app.route('/api/view', methods=['GET'])
def cashclaw_view_task():
    task_id = request.args.get('task')
    # Placeholder return
    return jsonify({"task": {"id": task_id, "description": "Mocked task from DualBrain", "status": "open", "messages": []}})

@app.route('/api/quote', methods=['POST'])
def cashclaw_quote_task():
    data = request.json
    task_id = data.get("taskId")
    price_eth = data.get("priceEth")
    message = data.get("message")

    # In full implementation:
    # 1. Initialize BrowserAgent
    # 2. Call FreelanceAgent.submit_proposal(job_data={"title": task_id}, branding_context=...)
    return jsonify({"status": "success", "message": f"Quoted {price_eth} on {task_id}"})

@app.route('/api/decline', methods=['POST'])
def cashclaw_decline_task():
    data = request.json
    return jsonify({"status": "success"})

@app.route('/api/submit', methods=['POST'])
def cashclaw_submit_work():
    data = request.json
    task_id = data.get("taskId")
    result = data.get("result")

    # In full implementation:
    # Call FreelanceAgent.deliver_work(job_data={"title": task_id}, file_path=...)
    return jsonify({"status": "success", "message": f"Work submitted for {task_id}"})

@app.route('/api/message', methods=['POST'])
def cashclaw_send_message():
    data = request.json
    task_id = data.get("taskId")
    content = data.get("content")

    # In full implementation:
    # Call FreelanceAgent.check_messages_and_negotiate() or a dedicated reply method
    return jsonify({"status": "success", "message": f"Message sent to {task_id}"})

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=3778)
