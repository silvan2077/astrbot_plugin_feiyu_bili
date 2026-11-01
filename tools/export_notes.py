"""Export public DSH notes to a portable JSON file; no network operations."""
import argparse
import json
import pathlib
import re

BV=r'BV[A-Za-z0-9]{10}'
DATE=r'\d{4}-\d{2}-\d{2}'

def clean(value):
    value=re.sub(r'[A-Za-z]:[\\/][^\s）)]+','[本机路径]',value)
    value=re.sub(r'(?i)(token|sessdata|bili_jct|api_key)\s*[=:]\s*[^\s;,]+',r'\1=[redacted]',value)
    return value.strip()[:6000]

def export(home):
    records={}
    reports=home/'reports'
    if reports.exists():
        for f in sorted(reports.glob('*.md')):
            match=re.fullmatch('('+BV+')-('+DATE+')'+r'\.md',f.name)
            if not match or f.is_symlink() or f.stat().st_size>100000:continue
            fields={}
            for line in f.read_text(encoding='utf-8-sig').splitlines():
                m=re.match(r'^-\s*(?:\*\*)?(标题|UP|为什么值得|一句话|评论区)(?:\*\*)?\s*[：:]\s*(.*)',line)
                if m:fields[m[1]]=clean(m[2])
            if not fields.get('标题'):continue
            bv,date=match.groups()
            records[(date,bv)]={'date':date,'bvid':bv,'title':fields['标题'],'up':fields.get('UP',''),'status':'picked','summary':fields.get('为什么值得',''),'thought':fields.get('一句话',''),'comments':fields.get('评论区','')}
    seen=home/'seen.md'
    if seen.exists() and not seen.is_symlink() and seen.stat().st_size<2000000:
        for line in seen.read_text(encoding='utf-8-sig').splitlines():
            cells=[clean(x) for x in line.strip().strip('|').split('|')]
            if len(cells)<5 or not re.fullmatch(DATE,cells[0]) or not re.fullmatch(BV,cells[1]):continue
            date,bv,title,up,status=cells[:5]
            key=(date,bv)
            if key not in records:records[key]={'date':date,'bvid':bv,'title':title,'up':up,'status':'skipped' if '跳过' in status else 'seen','summary':'','thought':'','comments':''}
            if '跳过' in status:
                records[key]['status']='skipped'
    return sorted(records.values(),key=lambda x:(x['date'],x['bvid']),reverse=True)[:5000]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=pathlib.Path,required=True,help='DSH bili-duty directory')
    parser.add_argument('--output',type=pathlib.Path,required=True,help='Destination JSON file')
    args=parser.parse_args()
    if not args.home.is_dir():parser.error('--home must be an existing directory')
    records=export(args.home)
    args.output.write_text(json.dumps({'version':1,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Exported records:',len(records))

if __name__=='__main__':main()
