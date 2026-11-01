"""Durable delivery accounting. Unknown outcomes require operator resolution."""
import sqlite3
import json
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))

class State:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS shares(bv TEXT PRIMARY KEY, ts REAL, day TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS cache(bv TEXT PRIMARY KEY,source TEXT,body TEXT);
        ''')
        # A process may have died between submission and acknowledgement.
        with self.db:self.db.execute("UPDATE shares SET status='unknown' WHERE status='sending'")
    def close(self): self.db.close()
    def get(self,k,default=''):
        r=self.db.execute('SELECT v FROM kv WHERE k=?',(k,)).fetchone()
        return r[0] if r else default
    def set(self,k,v):
        with self.db:self.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(k,str(v)))
    def reply(self): self.set('unanswered',0)
    def reset_owner(self,owner):
        with self.db:
            self.db.execute("DELETE FROM kv WHERE k IN ('umo','last_content','last_share','followup_shares') OR k LIKE 'biliread_detail:%'")
            self.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('bound_owner',str(owner)))
    def remember_share(self,info,message,now):
        try:rows=json.loads(self.get('followup_shares','[]'))
        except (ValueError,TypeError):rows=[]
        if not isinstance(rows,list):rows=[]
        rows=[r for r in rows if isinstance(r,dict) and r.get('bvid')!=info['bvid']]
        rows.append({**info,'message':message[:600],'ts':now})
        self.set('followup_shares',json.dumps(rows[-12:],ensure_ascii=False))
    def seen(self,bv):
        return self.db.execute("SELECT 1 FROM shares WHERE bv=? AND status!='failed'",(bv,)).fetchone() is not None
    def allowed(self,now,daily=3,gap=7200):
        t=datetime.fromtimestamp(now,CST)
        if 1<=t.hour<10:return 'quiet'
        if self.db.execute("SELECT 1 FROM shares WHERE status IN ('sending','unknown')").fetchone():return 'unknown'
        count=self.db.execute("SELECT COUNT(*) FROM shares WHERE day=? AND status='sent'",(t.date().isoformat(),)).fetchone()[0]
        if count>=daily:return 'daily'
        if int(self.get('unanswered','0'))>=2:return 'unanswered'
        last=self.db.execute("SELECT MAX(ts) FROM shares WHERE status='sent'").fetchone()[0]
        if last is not None and now-last<gap:return 'gap'
        return ''
    def reserve(self,bv,now):
        if self.seen(bv):raise ValueError('already shared or unknown')
        with self.db:self.db.execute('INSERT OR REPLACE INTO shares VALUES(?,?,?,?)',(bv,now,datetime.fromtimestamp(now,CST).date().isoformat(),'sending'))
    def finish(self,bv,status):
        if status not in ('sent','failed','unknown'):raise ValueError('bad status')
        with self.db:
            old=self.db.execute('SELECT status FROM shares WHERE bv=?',(bv,)).fetchone()
            self.db.execute('UPDATE shares SET status=? WHERE bv=?',(status,bv))
            if status=='sent' and old and old[0]!='sent':
                self.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('unanswered',str(int(self.get('unanswered','0'))+1)))
    def cache(self,bv,source,body):
        with self.db:self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(bv,source,body[:24000]))
    def cached(self,bv):return self.db.execute('SELECT source,body FROM cache WHERE bv=?',(bv,)).fetchone()
