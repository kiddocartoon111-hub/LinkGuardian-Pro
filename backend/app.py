from flask import Flask, request, jsonify, session
from flask_cors import CORS
from supabase import create_client
import os
from dotenv import load_dotenv
from monitor import LinkMonitor
import hashlib
from datetime import datetime, timedelta
import telegram

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
CORS(app)

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
monitor = LinkMonitor()
telegram_bot = telegram.Bot(token=os.getenv('TELEGRAM_TOKEN')) if os.getenv('TELEGRAM_TOKEN') else None

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    hashed = hashlib.sha256(data['password'].encode()).hexdigest()
    try:
        user = supabase.table('users').insert({
            'email': data['email'], 'password': hashed, 'full_name': data['full_name'],
            'plan': 'free', 'join_date': datetime.now().date().isoformat()
        }).execute()
        return jsonify({'success': True, 'user': user.data[0]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    hashed = hashlib.sha256(data['password'].encode()).hexdigest()
    user = supabase.table('users').select('*').eq('email', data['email']).eq('password', hashed).execute()
    if user.data:
        session['user_id'] = user.data[0]['id']
        return jsonify({'success': True, 'user': user.data[0]})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True})

@app.route('/api/user', methods=['GET'])
def get_user():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user = supabase.table('users').select('*').eq('id', session['user_id']).execute()
    return jsonify(user.data[0])

@app.route('/api/check-single', methods=['POST'])
def check_single():
    data = request.json
    result = monitor.check_link(data['url'], data.get('platform', 'generic'))
    return jsonify(result)

@app.route('/api/links', methods=['GET'])
def get_links():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    links = supabase.table('links').select('*').eq('user_id', session['user_id']).execute()
    return jsonify(links.data)

@app.route('/api/links', methods=['POST'])
def add_link():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    user = supabase.table('users').select('plan').eq('id', session['user_id']).execute()
    limits = {'free':5, 'pro':20, 'business':100, 'agency':500}
    count = supabase.table('links').select('*', count='exact').eq('user_id', session['user_id']).execute()
    if count.count >= limits.get(user.data[0]['plan'], 5):
        return jsonify({'error': 'Link limit reached'}), 403
    link = supabase.table('links').insert({
        'user_id': session['user_id'], 'name': data['name'], 'url': data['url'],
        'platform': data.get('platform', 'generic'), 'check_frequency': data.get('frequency', 'daily')
    }).execute()
    return jsonify(link.data[0])

@app.route('/api/links/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    supabase.table('links').delete().eq('id', link_id).eq('user_id', session['user_id']).execute()
    return jsonify({'success': True})

@app.route('/api/links/<link_id>/check', methods=['POST'])
def manual_check(link_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    link = supabase.table('links').select('*').eq('id', link_id).eq('user_id', session['user_id']).execute()
    if not link.data:
        return jsonify({'error': 'Link not found'}), 404
    link_data = link.data[0]
    result = monitor.check_link(link_data['url'], link_data.get('platform', 'generic'))
    # Save history
    supabase.table('check_history').insert({
        'link_id': link_id, 'status': result['status'], 'response_time': result['response_time'],
        'error_message': result.get('error'), 'layer_used': result.get('layer_used')
    }).execute()
    supabase.table('links').update({
        'last_checked': datetime.now().isoformat(), 'last_status': result['status'],
        'last_response_time': result['response_time']
    }).eq('id', link_id).execute()
    # Send alert if not active
    if result['status'] != 'active':
        send_alert(session['user_id'], link_data, result)
    return jsonify(result)

def send_alert(user_id, link_data, result):
    if not telegram_bot:
        return
    user = supabase.table('users').select('telegram_chat_id').eq('id', user_id).execute()
    if not user.data or not user.data[0].get('telegram_chat_id'):
        return
    emoji = {'broken':'❌','out_of_stock':'📦','error':'🚨'}.get(result['status'],'⚠️')
    msg = f"{emoji} *Link Alert*\n\nLink: {link_data['name']}\nStatus: {result['status'].upper()}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nLayer: {result.get('layer_used','unknown')}"
    try:
        telegram_bot.send_message(chat_id=user.data[0]['telegram_chat_id'], text=msg, parse_mode='Markdown')
    except:
        pass

@app.route('/api/cron/daily-check', methods=['POST'])
def scheduled_check():
    api_key = request.headers.get('X-API-Key')
    if api_key != os.getenv('CRON_API_KEY'):
        return jsonify({'error': 'Unauthorized'}), 401
    links = supabase.table('links').select('*, users!inner(*)').eq('is_active', True).execute()
    for link in links.data:
        user = link['users']
        join_date = datetime.fromisoformat(user['join_date'])
        plan_days = {'free':7, 'pro':30, 'business':30, 'agency':30}
        days = plan_days.get(user['plan'], 7)
        if datetime.now() > join_date + timedelta(days=days):
            continue
        result = monitor.check_link(link['url'], link.get('platform', 'generic'))
        supabase.table('check_history').insert({
            'link_id': link['id'], 'status': result['status'], 'response_time': result['response_time'],
            'error_message': result.get('error'), 'layer_used': result.get('layer_used')
        }).execute()
        supabase.table('links').update({
            'last_checked': datetime.now().isoformat(), 'last_status': result['status'],
            'last_response_time': result['response_time']
        }).eq('id', link['id']).execute()
        if result['status'] != 'active' and link['last_status'] != result['status']:
            send_alert(user['id'], link, result)
    return jsonify({'success': True, 'checked': len(links.data)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
