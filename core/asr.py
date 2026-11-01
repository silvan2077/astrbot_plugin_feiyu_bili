"""Fixed-endpoint ASR with TLS-preserving DNS fallback for the CN service."""
import ipaddress
import socket
import aiohttp
import httpx

class ResolvedHost(aiohttp.abc.AbstractResolver):
    def __init__(self,addresses):self.addresses=addresses
    async def resolve(self,host,port=0,family=socket.AF_INET):
        if host!='api.siliconflow.cn':raise OSError('Unexpected ASR hostname')
        return [{'hostname':host,'host':a,'port':port,'family':socket.AF_INET,'proto':0,'flags':0} for a in self.addresses]
    async def close(self):pass

async def transcribe_file(path,key,proxy):
    url='https://api.siliconflow.cn/v1/audio/transcriptions'
    headers={'Authorization':'Bearer '+key}
    try:
        async with httpx.AsyncClient(timeout=180,proxy=proxy or None) as client:
            with path.open('rb') as audio:
                r=await client.post(url,headers=headers,data={'model':'FunAudioLLM/SenseVoiceSmall'},files={'file':('audio.mp3',audio,'audio/mpeg')})
            if r.status_code!=200:raise RuntimeError('ASR HTTP '+str(r.status_code))
            return str(r.json().get('text',''))[:24000]
    except httpx.ConnectError:
        # Connection establishment failed before HTTP upload. Retry once directly
        # with public DoH results; preserve hostname/SNI/certificate verification.
        async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
            dns=await client.get('https://dns.alidns.com/resolve',params={'name':'api.siliconflow.cn','type':'A'})
            dns.raise_for_status();answer=dns.json()
        addresses=[a['data'] for a in answer.get('Answer',[]) if a.get('type')==1 and ipaddress.ip_address(a['data']).is_global]
        if not addresses:raise RuntimeError('ASR public DNS returned no global address')
        connector=aiohttp.TCPConnector(resolver=ResolvedHost(addresses))
        with path.open('rb') as audio:
            form=aiohttp.FormData();form.add_field('model','FunAudioLLM/SenseVoiceSmall');form.add_field('file',audio,filename='audio.mp3',content_type='audio/mpeg')
            async with aiohttp.ClientSession(connector=connector,timeout=aiohttp.ClientTimeout(total=180)) as client:
                async with client.post(url,headers=headers,data=form,allow_redirects=False) as r:
                    if r.status!=200:raise RuntimeError('ASR direct HTTP '+str(r.status))
                    return str((await r.json()).get('text',''))[:24000]
