from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, requests, json
from datetime import datetime, timedelta
import threading, time

app = Flask(__name__)

LINE_TOKEN = os.environ.get('LINE_TOKEN', '').strip()
LINE_SECRET = os.environ.get('LINE_SECRET', '').strip()
GAS_URL = os.environ.get('GAS_URL', '').strip()
USER_ID = os.environ.get('USER_ID', '').strip()

line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

def load_data():
    try:
        r = requests.get(GAS_URL + '?action=load', timeout=10)
        return r.json()
    except:
        return {}

def send_message(text):
    if USER_ID:
        line_bot_api.push_message(USER_ID, TextSendMessage(text=text))

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route('/ping', methods=['GET'])
def ping():
    return 'pong'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    data = load_data()

    if text in ['報表', '業績', '本月業績']:
        deals = data.get('deals', [])
        now = datetime.now()
        month_deals = [d for d in deals if str(d.get('date',''))[:7] == now.strftime('%Y-%m')]
        total = sum(int(float(str(d.get('amount', 0)).replace(',',''))) for d in month_deals)
        reply = f"📊 {now.strftime('%Y年%m月')} 業績\n"
        reply += f"成交筆數：{len(month_deals)} 筆\n"
        reply += f"含稅總額：NT$ {total:,}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif text in ['今日行程', '今天', '行程']:
        events = data.get('events', [])
        today = datetime.now().strftime('%Y-%m-%d')
        today_events = [e for e in events if str(e.get('date',''))[:10] == today]
        if today_events:
            reply = f"📅 今日行程（{today}）\n"
            for e in today_events:
                reply += f"\n• {e.get('time','')} {e.get('title','')}"
        else:
            reply = f"📅 今日（{today}）沒有行程"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif text in ['待辦', '待辦事項']:
        todos = data.get('todos', [])
        pending = [t for t in todos if not t.get('done')]
        if pending:
            reply = f"📝 待辦事項（{len(pending)} 件）\n"
            for t in pending[:10]:
                reply += f"\n• {t.get('text','')}"
        else:
            reply = "📝 目前沒有待辦事項！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif text in ['客戶', '客戶數']:
        clients = data.get('clients', [])
        total = len(clients)
        won = len([c for c in clients if c.get('status') == '成交'])
        reply = f"👥 客戶總數：{total} 位\n已成交：{won} 位\n成交率：{round(won/total*100) if total else 0}%"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    else:
        reply = ("🤖 MAXI 助理指令：\n\n"
                 "📊 報表 → 本月業績\n"
                 "📅 今日行程 → 今天的行程\n"
                 "📝 待辦 → 待辦事項\n"
                 "👥 客戶 → 客戶統計")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# 排程提醒
def check_reminders():
    while True:
        try:
            now = datetime.now()
            data = load_data()
            events = data.get('events', [])
            today = now.strftime('%Y-%m-%d')

            for e in events:
                edate = str(e.get('date',''))[:10]
                etime = str(e.get('time',''))
                title = e.get('title','')
                if edate != today or not etime or not title:
                    continue
                try:
                    h, m = etime.split(':')
                    event_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                    diff = (event_dt - now).total_seconds() / 60
                    if 59 <= diff <= 61:
                        send_message(f"⏰ 1小時後提醒\n{etime} {title}")
                    elif 29 <= diff <= 31:
                        send_message(f"⏰ 30分鐘後提醒\n{etime} {title}")
                except:
                    pass
        except:
            pass
        time.sleep(60)

# 早安提醒（每天早上9點）
def morning_reminder():
    while True:
        try:
            now = datetime.now()
            if now.hour == 9 and now.minute == 0:
                data = load_data()
                events = data.get('events', [])
                today = now.strftime('%Y-%m-%d')
                today_events = [e for e in events if str(e.get('date',''))[:10] == today]
                todos = data.get('todos', [])
                pending = [t for t in todos if not t.get('done')]

                msg = f"🌅 早安！今日 {now.strftime('%m/%d')} 摘要\n"
                if today_events:
                    msg += f"\n📅 今日行程（{len(today_events)} 件）"
                    for e in today_events:
                        msg += f"\n• {e.get('time','')} {e.get('title','')}"
                else:
                    msg += "\n📅 今日無行程"
                if pending:
                    msg += f"\n\n📝 待辦事項 {len(pending)} 件未完成"
                send_message(msg)
        except:
            pass
        time.sleep(60)

if __name__ == '__main__':
    t1 = threading.Thread(target=check_reminders, daemon=True)
    t1.start()
    t2 = threading.Thread(target=morning_reminder, daemon=True)
    t2.start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
