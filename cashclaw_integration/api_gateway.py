from flask import Flask, request, jsonify
import sys
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# We would import our agents here but for now just mock them since we need to know the full structure
# from freelance_agent import FreelanceAgent
# from fiverr_agent import FiverrAgent
# from browser_agent import BrowserAgent
# from api_client import GeminiClient

@app.route('/api/inbox', methods=['GET'])
def get_inbox():
    # Return mocked or actual inbox
    return jsonify({"tasks": []})

@app.route('/api/view', methods=['GET'])
def view_task():
    task_id = request.args.get('task')
    # return task details
    return jsonify({"task": {"id": task_id, "description": "Mocked task"}})

@app.route('/api/quote', methods=['POST'])
def quote_task():
    data = request.json
    # call agent to quote
    return jsonify({"status": "success"})

@app.route('/api/submit', methods=['POST'])
def submit_work():
    data = request.json
    return jsonify({"status": "success"})

@app.route('/api/message', methods=['POST'])
def send_message():
    data = request.json
    return jsonify({"status": "success"})

@app.route('/api/decline', methods=['POST'])
def decline_task():
    data = request.json
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(port=3778, debug=True)
