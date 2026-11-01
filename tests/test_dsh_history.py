import pathlib
import tempfile
import unittest
import asyncio
import ast
import datetime
import json
import types
from test_feiyu_bili import load

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.h=load('history').History(pathlib.Path(self.tmp.name)/'h.db')
    def tearDown(self):self.h.close();self.tmp.cleanup()
    def record(self,**kw):return {'bvid':'BV1nVHP6iEVQ','date':'2026-10-31','title':'video','up':'author','status':'picked','summary':'AI自由意志','thought':'interesting',**kw}
    def test_upsert_and_search(self):
        self.h.ingest([self.record()]);self.h.ingest([self.record(thought='new')])
        self.assertEqual(len(self.h.query('2026-10-31')),1)
        self.assertEqual(self.h.query(keyword='自由')[0]['thought'],'new')
        self.assertEqual(self.h.query(keyword='BV1nVHP6iEVQ')[0]['title'],'video')
    def test_skip_not_recommended(self):
        self.h.ingest([self.record(status='skipped')])
        self.assertEqual(self.h.candidates('2026-10-30'),[])
        self.assertEqual(len(self.h.query('2026-10-31')),1)
    def test_latest_skip_overrides_old_pick(self):
        self.h.ingest([self.record(date='2026-10-30'),self.record(status='skipped')])
        self.assertEqual(self.h.candidates('2026-10-29'),[])
    def test_reject_bad_records_atomically(self):
        with self.assertRaises(ValueError):self.h.ingest([self.record(),self.record(bvid='../x')])
        self.assertEqual(self.h.query(),[])
    def test_parse_report_and_seen_only(self):
        import importlib.util
        p=pathlib.Path(__file__).resolve().parents[1]/'tools/export_notes.py'
        spec=importlib.util.spec_from_file_location('dsh_sync',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        root=pathlib.Path(self.tmp.name);(root/'reports').mkdir()
        (root/'reports/BV1nVHP6iEVQ-2026-10-31.md').write_text('> private path C:\\secret\\config.json\n- 标题：猫\n- UP：某人\n- 为什么值得：内容\n- 一句话：感想',encoding='utf-8')
        (root/'seen.md').write_text('| 2026-10-31 | BV1NWxz6nEjN | 另一条 | UP | 跳过 |',encoding='utf-8')
        records=m.export(root)
        self.assertEqual(len(records),2);self.assertNotIn('secret',str(records))
        self.assertEqual(records[0]['status'],'picked')
        self.assertEqual(records[1]['status'],'skipped')
    def test_tool_owner_gate_and_keyword_lookup(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'main.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));m=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='feiyu_bili_history');m.decorator_list=[]
        ns={'AstrMessageEvent':object,'json':json,'datetime':datetime.datetime,'timezone':datetime.timezone,'timedelta':datetime.timedelta};exec(compile(ast.Module(body=[m],type_ignores=[]),'tool','exec'),ns)
        self.h.ingest([self.record()]);obj=types.SimpleNamespace(owner_event=lambda e:False,history=self.h)
        self.assertIn('只允许',asyncio.run(ns['feiyu_bili_history'](obj,object())))
        obj.owner_event=lambda e:True
        self.assertIn('AI自由意志',asyncio.run(ns['feiyu_bili_history'](obj,object(),keyword='BV1nVHP6iEVQ')))
    def test_dsh_source_uses_notes_and_never_downloads(self):
        self.h.ingest([self.record()]);client=load('history').DSHClient(self.h)
        info,basis,text=asyncio.run(client.content('BV1nVHP6iEVQ'))
        self.assertEqual(basis,'dsh_notes');self.assertIn('AI自由意志',text);self.assertEqual(info['duration'],0)
