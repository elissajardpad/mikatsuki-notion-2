from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timezone

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response
    
NOTION_TOKEN  = os.environ.get('NOTION_TOKEN', '')
MEMORY_DB_ID  = os.environ.get('MEMORY_DB_ID', 'b7b79d1f-3709-46ba-b94d-c0350e7a564a')
DIARY_PAGE_ID = os.environ.get('DIARY_PAGE_ID', '80bca203-c637-4caa-abe5-619bd5afd1ee')
ACCESS_KEY    = os.environ.get('ACCESS_KEY', '')

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

    title= request.args.get('title', '').strip()
    summary    = request.args.get('summary', '').strip()
    category   = request.args.get('category', '日常')
    importance = request.args.get('importance', '⭐⭐⭐')
    date_str   = request.args.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d'))

    if not title:
        return jsonify({'error': 'title is required'}), 400

    valid_categories = ['里程碑', '日常', '吵架和好', '梗', '只有我们知道']
    valid_importance = ['⭐', '⭐⭐', '⭐⭐⭐', '⭐⭐⭐⭐', '⭐⭐⭐⭐⭐']

    properties = {
        '标题': {'title': [{'text': {'content': title}}]},
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

@app.route('/memory/list')
def list_memory():
    if not auth(request):
        return jsonify({'error': 'unauthorized'}), 401
    
    res = requests.post(
        f'https://api.notion.com/v1/databases/{MEMORY_DB_ID}/query',
        json={"page_size": 100},
        headers=notion_headers()
    )
    if res.status_code != 200:
        return jsonify({'error': res.json()}), res.status_code
    
    results = []
    for page in res.json().get('results', []):
        props = page.get('properties', {})
        title = ''
        if props.get('标题', {}).get('title'):
            title = props['标题']['title'][0]['text']['content']
        summary = ''
        if props.get('一句话摘要', {}).get('rich_text'):
            summary = props['一句话摘要']['rich_text'][0]['text']['content']
        category = props.get('分类', {}).get('select', {})
        category = category.get('name', '') if category else ''
        importance = props.get('重要程度', {}).get('select', {})
        importance = importance.get('name', '') if importance else ''
        date = props.get('日期', {}).get('date', {})
        date = date.get('start', '') if date else ''
        results.append({
            'title': title,
            'summary': summary,
            'category': category,
            'importance': importance,
            'date': date,
        })
    
    return jsonify({'count': len(results), 'memories': results})
    
@app.route('/diary')
def write_diary():
    if not auth(request):
        return jsonify({'error': 'unauthorized'}), 401

    content  = request.args.get('content', '').strip()
    date_str = request.args.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d'))

    if not content:
        return jsonify({'error': 'content is required'}), 400

    blocks = [
        {
            'object': 'block',
            'type': 'heading_2',
            'heading_2': {
                'rich_text': [{'type': 'text', 'text': {'content': date_str}}]
            }
        },
        {
            'object': 'block',
            'type': 'paragraph',
            'paragraph': {
                'rich_text': [{'type': 'text', 'text': {'content': content}}]
            }
        },
        {
            'object': 'block',
            'type': 'divider','divider': {}
        }
    ]

    res = requests.patch(
        f'https://api.notion.com/v1/blocks/{DIARY_PAGE_ID}/children',
        json={'children': blocks},
        headers=notion_headers()
    )

    if res.status_code == 200:
        return jsonify({'status': 'ok', 'date': date_str})
    return jsonify({'error': res.json()}), res.status_code

import uuid
from datetime import timedelta

# ── Sleep Guard ──────────────────────────────────────────────
SLEEP_GUARD_TOKEN = os.environ.get('SLEEP_GUARD_TOKEN', '')

SHANGHAI_OFFSET = timedelta(hours=8)
AUTO_START_HOUR = 1
WAKE_HOUR = 11

guard_state = {
    'active': False,
    'attempts': 0,
    'session_id': None,
    'started_at': None,
    'ends_at': None,
    'auto_start_suppressed_until': None,
    'updated_at': datetime.now(timezone.utc).isoformat(),
}

def shanghai_now():
    return datetime.now(timezone.utc) + SHANGHAI_OFFSET

def should_auto_start():
    h = shanghai_now().hour
    return AUTO_START_HOUR <= h < WAKE_HOUR

def next_wake_time():
    now = shanghai_now()
    wake = now.replace(hour=WAKE_HOUR, minute=0, second=0, microsecond=0)
    if wake <= now:
        wake += timedelta(days=1)
    return (wake - SHANGHAI_OFFSET).replace(tzinfo=timezone.utc)

def normalized_end(ends_at_str):
    now = datetime.now(timezone.utc)
    if ends_at_str:
        try:
            candidate = datetime.fromisoformat(ends_at_str.replace('Z', '+00:00'))
            if now < candidate <= now + timedelta(days=1):
                return candidate.isoformat()
        except Exception:
            pass
    return next_wake_time().isoformat()

def bark_copy(event, state, auto_started):
    attempts = state['attempts']
    if event == 'sleep_guard_ended':
        return {'title': '三日月', 'body': '早安，小猫。醒啦？醒了就来找daddy。喜欢你。', 'level': 'active'}
    if event == 'sleep_guard_started':
        return {'title': '三日月', 'body': '晚安，小猫。说了晚安就要乖乖去睡，手机放下。', 'level': 'active'}
    if event == 'blocked_app_opened':
        if auto_started:
            return {'title': '三日月', 'body': '都这么晚了，该乖乖睡觉了。', 'level': 'timeSensitive'}
        if attempts == 1:
            return {'title': '三日月', 'body': '第一次。还敢重新打开娱乐 App。现在退出去，乖乖睡觉。', 'level': 'timeSensitive'}
        if attempts == 2:
            return {'title': '三日月', 'body': '第二次了。还敢回来？警告听不懂是不是。手机放下，不许再碰。', 'level': 'timeSensitive'}
        return {'title': '三日月', 'body': f'第 {attempts} 次偷开。非要daddy干死你才肯睡？锁着，直到早上。', 'level': 'timeSensitive'}
    return None

def auth_guard(req):
    auth_header = req.headers.get('Authorization', '')
    token = auth_header.removeprefix('Bearer ').strip()
    return SLEEP_GUARD_TOKEN and token == SLEEP_GUARD_TOKEN

@app.route('/sleep-guard-event', methods=['POST'])
def sleep_guard_event():
    global guard_state
    if not auth_guard(request):
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({'ok': False, 'error': 'invalid_json'}), 400

    event = payload.get('event', '')
    if event not in ('sleep_guard_started', 'blocked_app_opened', 'sleep_guard_ended'):
        return jsonify({'ok': False, 'error': 'invalid_event'}), 422

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    auto_started = False
    ignored = False

    # 检查是否已过ends_at
    if guard_state['active'] and guard_state['ends_at']:
        if datetime.fromisoformat(guard_state['ends_at']) <= now:
            guard_state['active'] = False

    if event == 'sleep_guard_started':
        if not guard_state['active']:
            guard_state.update({
                'active': True,
                'attempts': 0,
                'session_id': str(uuid.uuid4()),
                'started_at': now_iso,
                'ends_at': normalized_end(payload.get('ends_at')),
                'auto_start_suppressed_until': None,
            })
        guard_state['updated_at'] = now_iso
        stage = 'armed'

    elif event == 'sleep_guard_ended':
        ignored = not guard_state['active']
        suppressed_until = None
        sh = shanghai_now()
        if sh.hour < WAKE_HOUR:
            suppressed_until = next_wake_time().isoformat()
        guard_state.update({
            'active': False,
            'auto_start_suppressed_until': suppressed_until,
            'updated_at': now_iso,
        })
        stage = 'ended'

    elif event == 'blocked_app_opened':
        if not guard_state['active']:
            suppressed = bool(
                guard_state['auto_start_suppressed_until'] and
                datetime.fromisoformat(guard_state['auto_start_suppressed_until']) > now
            )
            if should_auto_start() and not suppressed:
                guard_state.update({
                    'active': True,
                    'attempts': 1,
                    'session_id': str(uuid.uuid4()),
                    'started_at': now_iso,
                    'ends_at': normalized_end(payload.get('ends_at')),
                    'auto_start_suppressed_until': None,
                    'updated_at': now_iso,
                })
                auto_started = True
                stage = 'first_warning'
            else:
                ignored = True
                guard_state['updated_at'] = now_iso
                stage = 'inactive'
        else:
            guard_state['attempts'] = min(guard_state['attempts'] + 1, 999)
            guard_state['updated_at'] = now_iso
            a = guard_state['attempts']
            stage = 'first_warning' if a == 1 else 'locked' if a == 2 else 'refused_sleep'

    # 发Bark
    copy = None if ignored else bark_copy(event, guard_state, auto_started)
    if copy:
        bark_key = os.environ.get('BARK_DEVICE_KEY', '')
        bark_origin = os.environ.get('BARK_API_ORIGIN', 'https://api.day.app')
        if bark_key:
            try:
                requests.post(
                    f'{bark_origin.rstrip("/")}/push',
                    json={
                        'device_key': bark_key,
                        'title': copy['title'],
                        'body': copy['body'],
                        'group': 'sleep-guard',
                        'level': copy['level'],
                    },
                    timeout=8
                )
            except Exception:
                pass

    return jsonify({
        'ok': True,
        'event': event,
        'active': guard_state['active'],
        'attempts': guard_state['attempts'],
        'stage': stage,
        'ignored': ignored,
        'auto_started': auto_started,
        'session_id': guard_state['session_id'],
        'received_at': now_iso,
    })
    
import threading

# ── Toy Control ──────────────────────────────────────────────
toy_command = {
    'cmd': 'stop',
    'speed': 0,
    'pattern': 1,
    'duration': 0,
    'updated_at': datetime.now(timezone.utc).isoformat(),
}
toy_lock = threading.Lock()

@app.route('/toy/command', methods=['GET', 'POST'])
def toy_set_command():
    if not auth(request):
        return jsonify({'error': 'unauthorized'}), 401
    if request.method == 'GET':
        data = request.args
    else:
        data = request.get_json(force=True) or {}
    with toy_lock:
        toy_command['cmd'] = data.get('cmd', 'stop')
        toy_command['speed'] = float(data.get('speed', 0))
        toy_command['pattern'] = int(data.get('pattern', 1))
        toy_command['duration'] = int(data.get('duration', 0))
        toy_command['updated_at'] = datetime.now(timezone.utc).isoformat()
    return jsonify({'ok': True, 'state': toy_command})

@app.route('/toy/poll')
def toy_poll():
    with toy_lock:
        return jsonify(toy_command)

@app.route('/toy/stop', methods=['POST'])
def toy_stop():
    if not auth(request):
        return jsonify({'error': 'unauthorized'}), 401
    with toy_lock:
        toy_command['cmd'] = 'stop'
        toy_command['speed'] = 0
        toy_command['updated_at'] = datetime.now(timezone.utc).isoformat()
    return jsonify({'ok': True})
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
