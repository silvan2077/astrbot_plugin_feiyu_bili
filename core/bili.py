"""Read-only client; WBI algorithm ported from SurfCore (see NOTICE)."""
import hashlib
import html
import re
import time
from urllib.parse import urlencode, urlsplit
import aiohttp

MIXIN = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]
def sign(params,key,stamp=None):
    p={**params,'wts':int(time.time()) if stamp is None else stamp}
    q=urlencode([(k,re.sub(r"[!'()*]",'',str(p[k]))) for k in sorted(p)])
    return q+'&w_rid='+hashlib.md5((q+key).encode()).hexdigest()
def payload(d):
    if d.get('code')!=0:raise RuntimeError('Bilibili API code='+str(d.get('code')))
    return d.get('data') or {}
def normalize(r):
    return {'bvid':r.get('bvid',''),'title':html.unescape(re.sub('<[^>]+>','',str(r.get('title','')))),
            'author':r.get('author',r.get('owner',{}).get('name','')),'description':str(r.get('description',r.get('desc','')))[:2000],
            'duration':r.get('duration',0)}
def asset_url(u):
    p=urlsplit(u);h=p.hostname or ''
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and any(h.endswith('.'+d) for d in ['hdslb.com','bilivideo.com','bilibili.com'])

class Bili:
    def __init__(self,proxy='',cookie=''):
        self.proxy=proxy or None
        self.headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36','Referer':'https://www.bilibili.com/'}
        self.cookie=cookie
    async def get(self,path,params=None,signed=False):
        if signed:
            nav=await self.get('/x/web-interface/nav')
            imgs=nav['wbi_img'];raw=''.join(imgs[k].rsplit('/',1)[-1].split('.')[0] for k in ['img_url','sub_url'])
            key=''.join(raw[i] for i in MIXIN)[:32]
            url='https://api.bilibili.com'+path+'?'+sign(params or {},key)
        else:url='https://api.bilibili.com'+path
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            h={**self.headers}
            if self.cookie:h['Cookie']=self.cookie
            async with s.get(url,params=None if signed else params,headers=h,proxy=self.proxy) as r:
                r.raise_for_status()
                data=await r.json()
                # Public nav returns -101 when logged out but still supplies WBI keys.
                if path=='/x/web-interface/nav' and data.get('code')==-101 and data.get('data',{}).get('wbi_img'):
                    return data['data']
                return payload(data)
    async def discover(self,keyword):
        if keyword=='热门':
            d=await self.get('/x/web-interface/popular',{'ps':8,'pn':1})
            return [normalize(v) for v in d.get('list',[])][:8]
        d=await self.get('/x/web-interface/wbi/search/type',{'search_type':'video','keyword':keyword,'page':1},True)
        return [normalize(v) for v in d.get('result',[]) if re.fullmatch(r'BV[A-Za-z0-9]{10}',v.get('bvid',''))][:8]
    async def asset(self,url,limit=25*1024*1024):
        if url.startswith('//'):url='https:'+url
        if url.startswith('http://'):url='https://'+url[len('http://'):]
        if not asset_url(url):raise RuntimeError('Unexpected Bilibili asset host')
        # Cookie is intentionally never sent to media/subtitle hosts.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.get(url,headers=self.headers,proxy=self.proxy,allow_redirects=False) as r:
                r.raise_for_status()
                if r.status!=200:raise RuntimeError('Unexpected asset redirect')
                out=bytearray()
                async for chunk in r.content.iter_chunked(65536):
                    out.extend(chunk)
                    if len(out)>limit:raise RuntimeError('Asset exceeds size limit')
                return bytes(out)
    async def content(self,bv):
        import json
        if not self.cookie:
            fingerprint=await self.get('/x/frontend/finger/spi')
            if fingerprint.get('b_3'):self.cookie='buvid3='+fingerprint['b_3']
        d=await self.get('/x/web-interface/view',{'bvid':bv})
        info=normalize(d);info['cid']=d['cid']
        try:
            sub=await self.get('/x/player/wbi/v2',{'bvid':bv,'cid':d['cid']},True)
            tracks=sub.get('subtitle',{}).get('subtitles',[])
            tracks.sort(key=lambda x:not x.get('lan','').startswith(('zh','ai-zh')))
            if tracks:
                body=json.loads(await self.asset(tracks[0]['subtitle_url'],2*1024*1024))
                text='\n'.join(x.get('content','') for x in body.get('body',[]))[:24000]
                if text:return info,'subtitle',text
        except (RuntimeError,aiohttp.ClientError,ValueError,KeyError):pass
        return info,'description',info['description']
    async def audio(self,info):
        d=await self.get('/x/player/wbi/playurl',{'bvid':info['bvid'],'cid':info['cid'],'fnval':16,'qn':16},True)
        streams=d.get('dash',{}).get('audio',[])
        if not streams:raise RuntimeError('No accessible audio stream')
        urls=[]
        for a in sorted(streams,key=lambda v:v.get('bandwidth',9999999)):
            for u in [a.get('baseUrl') or a.get('base_url')]+(a.get('backupUrl') or a.get('backup_url') or []):
                if u and u.startswith('http://'):u='https://'+u[7:]
                if u and asset_url(u) and u not in urls:urls.append(u)
        if not urls:raise RuntimeError('No allowlisted official Bilibili audio CDN')
        for u in urls[:2]:
            try:return await self.asset(u)
            except (aiohttp.ClientError,TimeoutError):continue
        raise RuntimeError('Official Bilibili audio CDN unavailable')
