from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timezone

app = Flask(__name__)

NOTION_TOKEN = os.environ.get('NOTION_TOKEN', '')
MEMORY_DB_ID = os.environ.get('MEMORY_DB_ID', 'b7b79d1f-3709-46ba-b94d-c0350e7a564a')
ACCESS_KEY   = os.environ.get('ACCESS_KEY', '')

def notion_headers():
    return {
        'Authorization': f'Bearer {NOTION_TOKEN}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }

def auth(req):
    return not ACCESS_KEY or req.args.get('key', '') == ACCESS_KEY

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/memory')
def write_memory():
    if not auth(request):
        return jsonify({'error': 'unauthorized'}), 401

    title      = request.args.get('title', '').strip()
    summary    = request.args.get('summary', '').strip()
    category   = request.args.get('category', '日常')
    importance = request.args.get('importance', '⭐⭐⭐')
    date_str   = request.args.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d'))

    if not title:
        return jsonify({'error': 'title is required'}), 400

    valid_categories  = ['里程碑', '日常', '吵架和好', '梗', '只有我们知道']
    valid_importance  = ['⭐', '⭐⭐⭐', '⭐⭐⭐⭐', '⭐⭐⭐⭐⭐']

    properties = {
        'title': {'title': [{'text': {'content': title}}]},
        '日期':  {'date':  {'start': date_str}},
    }

    if summary:
        properties['一句话摘要'] = {'rich_text': [{'text': {'content': summary}}]}
    if category in valid_categories:
        properties['分类'] = {'select': {'name': category}}
    if importance in valid_importance:
        properties['重要程度'] = {'select': {'name': importance}}

    res = requests.post(
        'https://api.notion.com/v1/pages',
        json={'parent': {'database_id': MEMORY_DB_ID}, 'properties': properties},
        headers=notion_headers()
    )

    if res.status_code == 200:
        return jsonify({'status': 'ok', 'written': title})
    return jsonify({'error': res.json()}), res.status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
