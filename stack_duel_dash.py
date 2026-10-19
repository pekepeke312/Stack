"""Stack Duel: two-phone multiplayer timing game with a Dash scoreboard.
Run: pip install dash qrcode pillow; python stack_duel_dash.py
Phone and computer must be on the same LAN (and firewall must allow TCP 8050).
"""
from __future__ import annotations
import base64
import io
import math
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from flask import jsonify, request, render_template_string
from dash import Dash, dcc, html
import qrcode

PORT = int(os.environ.get('STACK_PORT', '8050'))
SESSION_TIMEOUT = 4.0  # phone heartbeat expiry in seconds
BASE_SIZE = 4.0
MIN_OVERLAP = 0.025
PERFECT_TOLERANCE = 0.065
# Speed can be adjusted from Start_Stack_Duel.bat without editing Python.
# Movement units: board-coordinate units per second.
BASE_SPEED = float(os.environ.get('STACK_BASE_SPEED', '2.0'))
SPEED_GAIN = float(os.environ.get('STACK_SPEED_GAIN', '0.32'))
SPEED_EXTRA_AFTER = int(os.environ.get('STACK_EXTRA_AFTER', '12'))
SPEED_EXTRA_GAIN = float(os.environ.get('STACK_EXTRA_GAIN', '0.20'))
TRAVEL = 5.5


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip


def qr_data(url):
    img = qrcode.make(url)
    stream = io.BytesIO()
    img.save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


@dataclass
class Match:
    layers: list = field(default_factory=list)
    wasted: dict = field(default_factory=lambda: {1: 0.0, 2: 0.0})
    turn: int = 1
    done: bool = False
    message: str = ''
    move_started: float = 0.0
    nonce: int = 0
    last_player: int | None = None
    seen: dict = field(default_factory=dict)

    def reset(self):
        self.layers = [{'x': 0.0, 'y': 0.0, 'w': BASE_SIZE, 'd': BASE_SIZE}]
        self.wasted = {1: 0.0, 2: 0.0}
        self.turn = 1
        self.done = False
        self.message = 'Player 1 starts!'
        self.move_started = time.monotonic()
        self.nonce += 1
        self.last_player = None
        # Keep connected phones across a new match; a new round needs no rescan.

    def connected(self, now):
        return sorted(n for n, last in self.seen.items() if now - last < SESSION_TIMEOUT)

    def sync_turn(self, now):
        if self.done:
            return
        online = self.connected(now)
        if not online:
            self.turn = None
        elif len(online) == 1:
            self.turn = online[0]
        elif self.last_player in (1, 2):
            self.turn = 3 - self.last_player
        else:
            self.turn = 1

    @property
    def rounds(self):
        return len(self.layers) - 1

    def moving(self, now):
        old = self.layers[-1]
        axis = 'x' if self.rounds % 2 == 0 else 'y'
        speed = (BASE_SPEED + self.rounds * SPEED_GAIN
                 + max(0, self.rounds - SPEED_EXTRA_AFTER) * SPEED_EXTRA_GAIN)
        t = (now - self.move_started) * speed
        period = 2 * TRAVEL
        phase = t % (2 * period)
        offset = -TRAVEL + phase if phase < period else 3 * TRAVEL - phase
        return {**old, axis: old[axis] + offset, 'axis': axis}

    def place(self, who, now):
        self.sync_turn(now)
        if self.done or who != self.turn or who not in self.connected(now):
            return False
        old = self.layers[-1]
        mov = self.moving(now)
        axis = mov['axis']
        side = 'w' if axis == 'x' else 'd'
        diff = mov[axis] - old[axis]
        if abs(diff) <= PERFECT_TOLERANCE:
            diff = 0.0
        old_area = old['w'] * old['d']
        remaining = old[side] - abs(diff)
        self.last_player = who
        if remaining <= MIN_OVERLAP:
            self.wasted[who] += old_area
            self.done = True
            self.message = f'Player {who} MISSED!'
        else:
            new = dict(old)
            new[side] = remaining
            new[axis] = old[axis] + diff / 2
            self.layers.append(new)
            lost = old_area - new['w'] * new['d']
            self.wasted[who] += lost
            self.message = f'Player {who}: PERFECT!' if diff == 0 else f'Player {who} lost {lost:.2f} sq.'
            # Endless mode: only a complete miss finishes the match.
            self.sync_turn(now)
            self.move_started = now
        self.nonce += 1
        return True

    def snapshot(self, now):
        self.sync_turn(now)
        online = self.connected(now)
        mode = len(online)
        w1, w2 = self.wasted[1], self.wasted[2]
        winner = None
        if self.done and len(self.seen) > 1:
            winner = 'Draw' if abs(w1 - w2) < 1e-8 else ('Player 1' if w1 < w2 else 'Player 2')
        return {'layers': self.layers, 'moving': None if self.done or not online else self.moving(now),
                'mode': 'duel' if mode == 2 else ('solo' if mode == 1 else 'waiting'),
                'connected': online,
                'turn': None if self.done else self.turn, 'rounds': self.rounds,
                'total': None, 'wasted': {'1': round(w1, 4), '2': round(w2, 4)},
                'kept': round(self.layers[-1]['w'] * self.layers[-1]['d'], 4),
                'done': self.done, 'message': self.message, 'winner': winner,
                'nonce': self.nonce, 'last_player': self.last_player}


lock = threading.RLock()
match = Match()
match.reset()

app = Dash(__name__, title='Stack Duel')
server = app.server
ip = os.environ.get('STACK_PUBLIC_HOST', lan_ip())
base_url = f'http://{ip}:{PORT}'

# The Dash page is the PC display, including two scannable QR codes.
app.layout = html.Div([
    html.Div([
        html.Div([html.H1('STACK DUEL'), html.P('1 phone: solo · 2 phones: alternate turns on one tower · least wasted area wins')]),
        html.Div([html.Button('NEW MATCH', id='reset-btn', n_clicks=0), html.Div(id='reset-result')], className='reset'),
    ], className='top'),
    html.Div([
        html.Div([html.Div('PLAYER 1', className='label'),
                  html.Img(src=qr_data(base_url + '/play/1'), className='qr'),
                  html.A(base_url + '/play/1', href=base_url + '/play/1', target='_blank')], className='join'),
        html.Iframe(src='/arena', className='arena'),
        html.Div([html.Div('PLAYER 2', className='label'),
                  html.Img(src=qr_data(base_url + '/play/2'), className='qr'),
                  html.A(base_url + '/play/2', href=base_url + '/play/2', target='_blank')], className='join')
    ], className='center'),
    html.P('Both phones and this PC must use the same network. Open this dashboard on the PC; scan one QR per phone.', className='hint'),
], className='root')

app.index_string = '''<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
*{box-sizing:border-box}body{margin:0;background:#101524;color:#f6f8ff;font-family:system-ui,Arial}
.root{padding:20px;max-width:1600px;margin:auto}.top{display:flex;align-items:center;justify-content:space-between;gap:20px}
h1{letter-spacing:.16em;margin:0;color:#80ecdc}.top p,.hint{color:#aab4c8}
button{padding:14px 22px;background:#80ecdc;color:#13212b;font-weight:900;border:0;border-radius:12px;cursor:pointer}
.center{display:grid;grid-template-columns:160px minmax(0,1fr) 160px;gap:16px;align-items:center}
.join{background:#1a2437;border:1px solid #34425c;padding:13px;border-radius:16px;text-align:center;overflow-wrap:anywhere}
.label{font-weight:bold;letter-spacing:.1em;margin-bottom:10px}.qr{width:100%;border:8px solid white;border-radius:9px}
a{font-size:12px;color:#81ecdc}.arena{border:0;width:100%;height:650px;background:#111a2b;border-radius:16px}
.reset{text-align:right}.hint{text-align:center}
@media(max-width:980px){.center{grid-template-columns:1fr 1fr}.arena{grid-column:1/-1;grid-row:1}.join{grid-row:2}}
</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>'''

from dash import Input, Output, callback
@callback(Output('reset-result', 'children'), Input('reset-btn', 'n_clicks'), prevent_initial_call=True)
def reset_match(_):
    with lock:
        match.reset()
    return 'Match reset'


@server.get('/api/state')
def api_state():
    with lock:
        return jsonify(match.snapshot(time.monotonic()))


@server.post('/api/heartbeat/<int:n>')
def api_heartbeat(n):
    if n not in (1, 2):
        return jsonify({'error': 'Invalid player'}), 404
    with lock:
        now = time.monotonic()
        match.seen[n] = now
        return jsonify(match.snapshot(now))


@server.post('/api/place/<int:n>')
def api_place(n):
    if n not in (1, 2):
        return jsonify({'error': 'Invalid player'}), 404
    with lock:
        now = time.monotonic()
        ok = match.place(n, now)
        return jsonify(match.snapshot(now)), (200 if ok else 409)


ARENA_HTML = '''<!DOCTYPE html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}body{margin:0;background:#111a2b;color:white;font-family:system-ui}
.wrap{height:100vh;position:relative}canvas{display:block;width:100%;height:100%}
.hud{position:absolute;top:16px;left:16px;right:16px;display:flex;justify-content:space-between;gap:10px;pointer-events:none}
.score{background:#111b30df;border:1px solid #35455f;padding:12px 15px;border-radius:12px;min-width:125px}
.p1{border-top:4px solid #6ee7dc}.p2{border-top:4px solid #ffbe84}.active{box-shadow:0 0 0 3px #fff7}
.big{font-size:19px;font-weight:900}.small{color:#becae0;font-size:13px;margin-top:6px}
#notice{position:absolute;bottom:15px;left:0;right:0;text-align:center;font-size:21px;font-weight:800;color:#e5f2ff}
#winner{position:absolute;top:49%;left:50%;transform:translate(-50%,-50%);padding:25px 34px;border-radius:18px;background:#0a1323ef;font-size:30px;font-weight:900;display:none;z-index:3;text-align:center}
</style><body><div class="wrap"><canvas id="tower"></canvas>
<div class="hud"><div class="score p1" id="p1"><div class="big">PLAYER 1</div><div class="small" id="s1"></div></div>
<div class="score" id="middle"><div class="big" id="turn">CONNECTING</div><div class="small" id="round"></div></div>
<div class="score p2" id="p2"><div class="big">PLAYER 2</div><div class="small" id="s2"></div></div></div>
<div id="notice"></div><div id="winner"></div></div><script>
let state=null;const c=document.getElementById('tower');
function poly(ctx,pts,fill){ctx.beginPath();ctx.moveTo(...pts[0]);pts.slice(1).forEach(p=>ctx.lineTo(...p));ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle='#ffffff20';ctx.lineWidth=1.2;ctx.stroke();}
function draw(){const rect=c.getBoundingClientRect();const dpr=Math.min(devicePixelRatio||1,2),width=rect.width,height=rect.height;
 c.width=Math.max(1,width*dpr);c.height=Math.max(1,height*dpr);const ctx=c.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
 if(!state)return;const p=state, count=p.layers.length;
 // Keep the upper 28 layers readable even after hundreds of successful turns.
 const visible=28, first=Math.max(0,count-visible), displayCount=count-first;
 const scale=Math.min(width/12,height/14)*1.8,sx=scale*.86,sy=scale*.43;
 const level=Math.min(scale*.55,height/(displayCount+5)*.92);
 const ox=width*.5,oy=height*.82;
 const project=(x,y,z)=>[ox+(x-y)*sx,oy+(x+y)*sy-(z-first)*level];
 function block(o,i,color){let x=o.x,y=o.y,w=o.w,d=o.d,z=i;
 let A=project(x-w/2,y-d/2,z),B=project(x+w/2,y-d/2,z),C=project(x+w/2,y+d/2,z),D=project(x-w/2,y+d/2,z);
 let b=project(x+w/2,y-d/2,z-.8),cc=project(x+w/2,y+d/2,z-.8),dd=project(x-w/2,y+d/2,z-.8);
 poly(ctx,[D,C,cc,dd],'#2a586e');poly(ctx,[B,C,cc,b],'#347a8f');poly(ctx,[A,B,C,D],color);}
 p.layers.slice(first).forEach((b,i)=>{const z=i+first;block(b,z,z===0?'#6c8298':(z%2===1?'#6ee7dc':'#ffbe84'));});
 if(p.moving)block(p.moving,count,p.turn===1?'#b7fff2':'#ffe0bf');
 for(let n=1;n<=2;n++){document.getElementById('s'+n).textContent='Wasted '+p.wasted[n].toFixed(2)+' sq.';
 document.getElementById('p'+n).classList.toggle('active',p.turn===n);}
 document.getElementById('turn').textContent=p.done?'GAME OVER':p.mode==='waiting'?'SCAN A QR':(p.mode==='solo'?'SOLO · ':'DUEL · ')+'PLAYER '+p.turn+' TURN';
 document.getElementById('round').textContent='Placed '+p.rounds+' · ENDLESS';
 document.getElementById('notice').textContent=p.mode==='waiting'?'Scan either QR code to start':p.message;
 const w=document.getElementById('winner');w.style.display=p.winner?'block':'none';w.textContent=p.done&&p.mode==='solo'?'SOLO GAME OVER':p.winner?(p.winner==='Draw'?'DRAW!':p.winner.toUpperCase()+' WINS!'):'';w.style.display=p.done?'block':'none';
}
async function poll(){try{const r=await fetch('/api/state',{cache:'no-store'});if(r.ok)state=await r.json();}catch(e){}}
function frame(){draw();requestAnimationFrame(frame);}setInterval(poll,80);poll();requestAnimationFrame(frame);
</script></body></html>'''


PHONE_HTML = '''<!DOCTYPE html><html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<style>*{box-sizing:border-box}html,body{height:100%;margin:0;overflow:hidden;touch-action:manipulation;background:BG;color:#fff;font-family:system-ui}
#touch{height:100%;width:100%;display:flex;flex-direction:column;align-items:center;justify-content:space-between;padding:8vh 16px 10vh;user-select:none;touch-action:manipulation;cursor:pointer}
h1{font-size:clamp(24px,8vw,44px);margin:0}.info{text-align:center;font-size:20px;color:#bfd1e6}.tap{border-radius:50%;width:min(62vw,280px);height:min(62vw,280px);background:accent;color:#0c2230;display:flex;justify-content:center;align-items:center;font-size:34px;font-weight:900;box-shadow:0 0 0 16px #ffffff13}
.waiting .tap{background:#64748b;color:#d3dfeb}#msg{font-size:23px;text-align:center;font-weight:700}
</style><body><div id="touch" role="button" tabindex="0"><h1>PLAYER NUM</h1><div class="info" id="score">Connecting...</div><div class="tap" id="tap">WAIT</div><div id="msg">Connecting...</div></div>
<script>
const player=NUM;let busy=false;let game=null;
async function refresh(){try{const r=await fetch('/api/heartbeat/'+player,{method:'POST',cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();game=d;
 document.getElementById('score').textContent=`${d.mode==='solo'?'SOLO MODE':'DUEL MODE'} · Placed ${d.rounds} · ENDLESS · My waste ${d.wasted[player].toFixed(2)} sq.${d.mode==='duel'?' · Opponent '+d.wasted[3-player].toFixed(2)+' sq.':''}`;
 const active=!d.done&&d.turn===player;document.getElementById('touch').classList.toggle('waiting',!active);
 document.getElementById('tap').textContent=d.done?'END':active?'TAP!':'WAIT';
 document.getElementById('msg').textContent=d.done?(d.mode==='solo'?'SOLO FINISHED!':d.winner?(d.winner==='Draw'?'DRAW':d.winner+' WINS!'):'GAME OVER'):(active?'YOUR TURN! Tap to place':'Player '+d.turn+' is playing. Please wait.');
 }catch(e){document.getElementById('msg').textContent='Cannot connect to game server';}}
async function place(){if(busy||!game||game.done||game.turn!==player)return;busy=true;
 try{await fetch('/api/place/'+player,{method:'POST'});await refresh();}finally{setTimeout(()=>busy=false,180);}}
document.getElementById('touch').addEventListener('pointerdown',e=>{e.preventDefault();place();});
document.addEventListener('keydown',e=>{if(e.code==='Space'||e.code==='Enter'){e.preventDefault();place();}});
setInterval(refresh,180);refresh();
</script></body></html>'''


@server.get('/arena')
def arena():
    return ARENA_HTML


@server.get('/play/<int:n>')
def phone(n):
    if n not in (1, 2):
        return 'Player not found', 404
    return PHONE_HTML.replace('NUM', str(n)).replace('BG', '#12323d' if n == 1 else '#392b37').replace('accent', '#6ee7dc' if n == 1 else '#ffbe84')


if __name__ == '__main__':
    print(f'PC dashboard: http://127.0.0.1:{PORT}')
    print(f'LAN dashboard: {base_url}')
    print(f'Player 1: {base_url}/play/1')
    print(f'Player 2: {base_url}/play/2')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
