from flask import Flask, render_template_string, jsonify
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

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5000)
