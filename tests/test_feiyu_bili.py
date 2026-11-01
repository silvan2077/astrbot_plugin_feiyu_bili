import importlib.util
import pathlib
import tempfile
import unittest
import ast
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'core' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = load('state').State(pathlib.Path(self.tmp.name) / 'state.db')
    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()
    def at(self, hour, minute=0, day=1):
        return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc).timestamp()
    def test_quiet_boundaries(self):
        self.assertEqual(self.s.allowed(self.at(17)), 'quiet')  # 01:00 CST
        self.assertEqual(self.s.allowed(self.at(1,59)), 'quiet')
        self.assertEqual(self.s.allowed(self.at(2)), '')
    def test_unanswered_limit_and_reply(self):
        for bv, hour in [('BV1xx411c7mD',2),('BV1xx411c7mE',4)]:
            self.s.reserve(bv,self.at(hour));self.s.finish(bv,'sent')
        self.assertEqual(self.s.allowed(self.at(6)), 'unanswered')
        self.s.reply();self.assertEqual(self.s.allowed(self.at(6)), '')
    def test_gap_daily_and_restart_dedup(self):
        self.s.reserve('BV1',self.at(2));self.s.finish('BV1','sent');self.s.reply()
        self.assertEqual(self.s.allowed(self.at(3)), 'gap')
        for bv,h in [('BV2',4),('BV3',6)]:
            self.s.reserve(bv,self.at(h));self.s.finish(bv,'sent');self.s.reply()
        self.assertEqual(self.s.allowed(self.at(8)), 'daily')
        self.assertEqual(self.s.allowed(self.at(2,day=2)), '')
        self.assertTrue(self.s.seen('BV1'))
    def test_unknown_blocks_retry_but_not_counted_success(self):
        self.s.reserve('BV1',self.at(2));self.s.finish('BV1','unknown')
        self.assertTrue(self.s.seen('BV1'))
        self.assertEqual(self.s.allowed(self.at(4)), 'unknown')
        self.s.finish('BV1','failed')
        self.assertEqual(self.s.allowed(self.at(4)), '')
    def test_cache(self):
        self.s.cache('BV1','audio','hello');self.assertEqual(self.s.cached('BV1'),('audio','hello'))

class ClientTests(unittest.TestCase):
    def test_wbi_deterministic_and_clean(self):
        b=load('bili');q=b.sign({'keyword':"a!'()"},'x'*32,100)
        self.assertIn('keyword=a&',q);self.assertIn('wts=100',q);self.assertIn('w_rid=',q)
    def test_error_and_result_normalization(self):
        b=load('bili')
        with self.assertRaises(RuntimeError):b.payload({'code':-412})
        self.assertEqual(b.normalize({'bvid':'BV1xx411c7mD','title':'<em>cat</em>'})['title'],'cat')
    def test_public_asset_restriction(self):
        b=load('bili')
        self.assertFalse(b.asset_url('http://127.0.0.1/a'))
        self.assertFalse(b.asset_url('https://evil.example/a'))
        self.assertTrue(b.asset_url('https://aisubtitle.hdslb.com/a'))

class ScopeTests(unittest.TestCase):
    def test_only_owner_private_qq(self):
        tree=ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='owner_event')
        ns={};exec(compile(ast.Module(body=[method],type_ignores=[]),'scope','exec'),ns)
        owner=types.SimpleNamespace(config={'owner_qq':'123'})
        def event(uid='123',private=True,platform='aiocqhttp'):
            return types.SimpleNamespace(get_sender_id=lambda:uid,is_private_chat=lambda:private,get_platform_name=lambda:platform)
        self.assertTrue(ns['owner_event'](owner,event()))
        self.assertFalse(ns['owner_event'](owner,event(private=False)))
        self.assertFalse(ns['owner_event'](owner,event(uid='456')))
        self.assertFalse(ns['owner_event'](owner,event(platform='webchat')))
    def test_send_rechecks_switch_and_owner(self):
        import asyncio
        tree=ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='send')
        ns={'time':__import__('time'),'MessageChain':lambda x:x,'Plain':str}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'send','exec'),ns)
        called=[]
        async def send(*a):called.append(a);return True
        values={'umo':'qq:FriendMessage:123','bound_owner':'123','enabled':'False','last_reply':'0'}
        obj=types.SimpleNamespace(config={'owner_qq':'123'},state=types.SimpleNamespace(get=lambda k,d='':values.get(k,d)),context=types.SimpleNamespace(send_message=send))
        self.assertFalse(asyncio.run(ns['send'](obj,'hello')))
        values.update(enabled='True',bound_owner='999')
        self.assertFalse(asyncio.run(ns['send'](obj,'hello')))
        self.assertEqual(called,[])
    def test_qq_online_check_rejects_disconnected_bot(self):
        import asyncio
        from unittest.mock import AsyncMock
        tree=ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='online')
        ns={'asyncio':asyncio};exec(compile(ast.Module(body=[method],type_ignores=[]),'online','exec'),ns)
        bot=types.SimpleNamespace(get_status=AsyncMock(return_value={'online':True}))
        obj=types.SimpleNamespace(state=types.SimpleNamespace(get=lambda k:'qq:FriendMessage:123'),context=types.SimpleNamespace(get_platform_inst=lambda k:types.SimpleNamespace(bot=bot)))
        self.assertTrue(asyncio.run(ns['online'](obj)))
        bot.get_status.side_effect=ConnectionError()
        self.assertFalse(asyncio.run(ns['online'](obj)))

if __name__=='__main__': unittest.main()
