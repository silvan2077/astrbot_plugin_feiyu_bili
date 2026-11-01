"""Durable, bounded DSH viewing notes. No private chat or credentials."""
import datetime
import json
import re
import sqlite3

FIELDS=('date','bvid','title','up','status','summary','thought','comments')
def validate(records):
    if not isinstance(records,list) or len(records)>5000:raise ValueError('invalid record count')
    out=[]
    for r in records:
        if not isinstance(r,dict):raise ValueError('invalid record')
        item={k:str(r.get(k,'')) for k in FIELDS}
        if not re.fullmatch(r'BV[A-Za-z0-9]{10}',item['bvid']):raise ValueError('invalid bvid')
        datetime.date.fromisoformat(item['date'])
        if item['status'] not in ('picked','skipped','seen'):raise ValueError('invalid status')
        if any(len(v)>6000 for v in item.values()):raise ValueError('field too long')
        out.append(item)
    return out

class History:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=15)
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS videos(date TEXT,bvid TEXT,title TEXT,up TEXT,status TEXT,summary TEXT,thought TEXT,comments TEXT, PRIMARY KEY(date,bvid))')
        self.db.commit()
    def close(self):self.db.close()
    def ingest(self,records):
        rows=validate(records)
        with self.db:
            for r in rows:
                self.db.execute('INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?,?,?)',tuple(r[k] for k in FIELDS))
        return len(rows)
    def query(self,date='',keyword='',limit=8):
        terms=[];values=[]
        if date:
            datetime.date.fromisoformat(date);terms.append('date=?');values.append(date)
        if keyword:
            keyword=keyword[:100];terms.append('(instr(title,?) OR instr(summary,?) OR instr(bvid,?))');values.extend([keyword]*3)
        sql='SELECT * FROM videos'+(' WHERE '+' AND '.join(terms) if terms else '')+' ORDER BY date DESC,bvid LIMIT ?'
        values.append(max(1,min(int(limit),20)))
        return [dict(r) for r in self.db.execute(sql,values)]
    def candidates(self,since):
        return [dict(r) for r in self.db.execute("SELECT v.* FROM videos v JOIN (SELECT bvid,MAX(date) AS date FROM videos GROUP BY bvid) latest ON latest.bvid=v.bvid AND latest.date=v.date WHERE v.date>=? AND v.status='picked' AND v.summary!='' ORDER BY v.date DESC,v.bvid LIMIT 30",(since,))]
    def lookup(self,bv):
        r=self.db.execute('SELECT * FROM videos WHERE bvid=? ORDER BY date DESC LIMIT 1',(bv,)).fetchone()
        return dict(r) if r else None

class DSHClient:
    def __init__(self,history):self.history=history
    async def discover(self,keyword):
        today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
        return self.history.candidates((today-datetime.timedelta(days=7)).isoformat())
    async def content(self,bv):
        r=self.history.lookup(bv)
        if not r:raise RuntimeError('DSH record no longer exists')
        text=json.dumps({k:r[k] for k in ['summary','thought','comments']},ensure_ascii=False)
        return {'bvid':r['bvid'],'title':r['title'],'duration':0,'viewed_date':r['date']},'dsh_notes',text
