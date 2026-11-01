import asyncio
import ast
import json
import pathlib
import tempfile
import types
import unittest
from unittest.mock import AsyncMock
from test_feiyu_bili import load


class FollowupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=load('state').State(pathlib.Path(self.tmp.name)/'state.db')
        self.mod=load('followup')
        self.now=1793512800
        self.info={'bvid':'BV1xx411c7mD','title':'猫假装思考','basis':'DSH笔记','summary':'猫盯着镜头等待'}
        self.mod.remember_share(self.state,self.info,'这猫太像等消息的你了',self.now)
        self.classify=AsyncMock(return_value='{"bvid":"BV1xx411c7mD"}')
        self.read=AsyncMock(return_value=types.SimpleNamespace(completion_text='字幕显示作者讨论了等待回复的心理。'))
        self.reader=self.mod.Followup(self.state,self.classify,self.read)

    async def asyncTearDown(self):
        self.state.close();self.tmp.cleanup()

    async def test_semantic_match_reads_and_preserves_basis(self):
        result=await self.reader.enrich('他说的有道理吗',now=self.now+30)
        self.assertEqual(result['bvid'],self.info['bvid'])
        self.assertEqual(result['status'],'ok')
        self.assertIn('字幕显示',result['detail'])
        self.read.assert_awaited_once_with(self.info['bvid'])

    async def test_unrelated_and_bad_model_output_skip(self):
        for answer in ['{"bvid":""}','不确定','{"bvid":"BV1xx411c7mE"}']:
            self.classify.return_value=answer
            self.assertIsNone(await self.reader.enrich('明天吃什么',now=self.now+10))
        self.read.assert_not_awaited()

    async def test_explicit_quote_selects_older_video_not_latest(self):
        self.mod.remember_share(self.state,dict(self.info,bvid='BV1xx411c7mE',title='做饭'),'做饭视频',self.now+100)
        result=await self.reader.enrich('这里是什么意思',quoted='https://www.bilibili.com/video/BV1xx411c7mD',now=self.now+200)
        self.assertEqual(result['bvid'],self.info['bvid'])
        self.classify.assert_not_awaited()

    async def test_unknown_explicit_video_does_not_select_last_share(self):
        self.assertIsNone(await self.reader.enrich('看看BV1xx411c7mF',now=self.now+10))
        self.read.assert_not_awaited();self.classify.assert_not_awaited()

    async def test_cache_survives_new_reader(self):
        await self.reader.enrich('BV1xx411c7mD',now=self.now+10)
        another=self.mod.Followup(self.state,self.classify,self.read)
        result=await another.enrich('BV1xx411c7mD',now=self.now+20)
        self.assertTrue(result['cached']);self.assertEqual(self.read.await_count,1)

    async def test_failure_has_cooldown_and_is_not_success(self):
        self.read.return_value='视频《猫》暂无可用字幕，无法生成总结。'
        a=await self.reader.enrich('BV1xx411c7mD',now=self.now+10)
        b=await self.reader.enrich('BV1xx411c7mD',now=self.now+20)
        self.assertEqual(a['status'],'unavailable');self.assertEqual(b['status'],'unavailable')
        self.assertEqual(self.read.await_count,1)
        await self.reader.enrich('BV1xx411c7mD',now=self.now+400)
        self.assertEqual(self.read.await_count,2)

    async def test_timeout_does_not_break_chat(self):
        self.read.side_effect=asyncio.TimeoutError()
        result=await self.reader.enrich('BV1xx411c7mD',now=self.now+20)
        self.assertEqual(result['status'],'unavailable')
        self.assertNotIn('Traceback',result['detail'])

    async def test_old_share_requires_explicit_reference(self):
        self.assertIsNone(await self.reader.enrich('他说的对吗',now=self.now+90000))
        self.classify.assert_not_awaited()
        self.assertIsNotNone(await self.reader.enrich('BV1xx411c7mD',now=self.now+90000))

    async def test_concurrent_reads_are_deduplicated(self):
        async def slow(bvid):
            await asyncio.sleep(.01)
            return '有效字幕摘要'
        self.read.side_effect=slow
        await asyncio.gather(*[self.reader.enrich('BV1xx411c7mD',now=self.now+10) for _ in range(2)])
        self.assertEqual(self.read.await_count,1)

    async def test_cancel_is_propagated_and_retry_works(self):
        self.read.side_effect=asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.reader.enrich('BV1xx411c7mD',now=self.now+10)
        self.read.side_effect=None;self.read.return_value='重试成功的摘要'
        self.assertEqual((await self.reader.enrich('BV1xx411c7mD',now=self.now+11))['status'],'ok')

    async def test_classification_context_and_limit(self):
        await self.reader.enrich('后面呢',history='机器人：刚才讲的等待回复观点',now=self.now+10)
        prompt=self.classify.await_args.args[0]
        self.assertIn('等待回复观点',prompt);self.assertIn('猫假装思考',prompt)

    async def test_legacy_last_successful_share(self):
        self.state.set('followup_shares','[]')
        self.state.reserve(self.info['bvid'],self.now);self.state.finish(self.info['bvid'],'sent')
        self.state.set('last_content',json.dumps(self.info))
        self.assertIsNotNone(await self.reader.enrich('BV1xx411c7mD',now=self.now+5))


class HookTests(unittest.IsolatedAsyncioTestCase):
    def hook(self):
        source=pathlib.Path(__file__).resolve().parents[1]/'main.py'
        cls=next(x for x in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(x,ast.ClassDef))
        method=next(x for x in cls.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='enrich_followup')
        ns={'asyncio':asyncio,'json':json,'TextPart':lambda **kw:kw,
            'ContextWrapper':lambda **kw:types.SimpleNamespace(**kw),'AstrAgentContext':lambda **kw:types.SimpleNamespace(**kw),
            'logger':types.SimpleNamespace(info=lambda *a:None,warning=lambda *a:None)}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'hook','exec'),ns)
        return ns['enrich_followup']

    def objects(self):
        tool=types.SimpleNamespace(active=True,call=AsyncMock())
        event=types.SimpleNamespace(message_str='这个观点你怎么看',message_obj=types.SimpleNamespace(message=[
            types.SimpleNamespace(type='Reply',message_str='BV1xx411c7mD',chain=[])]))
        req=types.SimpleNamespace(prompt='这个观点你怎么看',func_tool=types.SimpleNamespace(get_tool=lambda name:tool),
            contexts=[{'role':'assistant','content':'视频谈了等待的心情'}],extra_user_content_parts=[])
        obj=types.SimpleNamespace(config={'owner_qq':'123'},owner_event=lambda e:True,
            state=types.SimpleNamespace(get=lambda k,d='':'123'),followup_context=None,
            context=types.SimpleNamespace(get_llm_tool_manager=lambda:types.SimpleNamespace(_check_tool_permission=AsyncMock(return_value=None))),
            followup=types.SimpleNamespace(enrich=AsyncMock(return_value={'bvid':'BV1xx411c7mD','status':'ok','cached':False,'detail':'先读取到的字幕摘要'})))
        return obj,event,req,tool

    async def test_read_completes_before_context_is_added(self):
        obj,event,req,tool=self.objects()
        async def enrich(*a,**kw):
            self.assertEqual(req.extra_user_content_parts,[])
            self.assertEqual(obj.followup_context,(tool,event))
            self.assertIn('BV1xx411c7mD',kw['quoted'])
            return {'bvid':'BV1xx411c7mD','status':'ok','cached':False,'detail':'先读取到的字幕摘要'}
        obj.followup.enrich.side_effect=enrich
        await self.hook()(obj,event,req)
        self.assertIn('先读取到的字幕摘要',req.extra_user_content_parts[0]['text'])
        self.assertIsNone(obj.followup_context)

    async def test_no_tool_permission_skips_even_if_cache_exists(self):
        for missing in [True,False]:
            obj,event,req,tool=self.objects()
            if missing:req.func_tool=None
            else:tool.active=False
            await self.hook()(obj,event,req)
            obj.followup.enrich.assert_not_awaited()

    async def test_group_non_owner_switch_and_commands_skip(self):
        for mode in ['group','other_owner','disabled','command']:
            obj,event,req,tool=self.objects()
            if mode=='group':obj.owner_event=lambda e:False
            if mode=='other_owner':obj.state.get=lambda *a:'456'
            if mode=='disabled':obj.config['followup_enabled']=False
            if mode=='command':req.prompt='/肥鱼B站 状态'
            await self.hook()(obj,event,req)
            obj.followup.enrich.assert_not_awaited()

    async def test_tool_exception_does_not_stop_normal_reply(self):
        obj,event,req,tool=self.objects();obj.followup.enrich.side_effect=RuntimeError('failure')
        await self.hook()(obj,event,req)
        self.assertEqual(req.extra_user_content_parts,[])
        self.assertIsNone(obj.followup_context)

    async def test_current_permission_rechecked_before_cached_content(self):
        obj,event,req,tool=self.objects()
        obj.context.get_llm_tool_manager=lambda:types.SimpleNamespace(_check_tool_permission=AsyncMock(return_value='denied'))
        await self.hook()(obj,event,req)
        obj.followup.enrich.assert_not_awaited()
        self.assertEqual(req.extra_user_content_parts,[])


class OwnerResetTests(unittest.TestCase):
    def test_owner_change_clears_private_followup_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=load('state').State(pathlib.Path(tmp)/'s.db')
            try:
                state.set('bound_owner','old');state.set('followup_shares','old private metadata')
                state.set('biliread_detail:BV1xx411c7mD','private details')
                state.set('last_content','private');state.set('umo','old session')
                state.reset_owner('new')
                self.assertEqual(state.get('followup_shares'),'')
                self.assertEqual(state.get('biliread_detail:BV1xx411c7mD'),'')
                self.assertEqual(state.get('last_content'),'')
                self.assertEqual(state.get('bound_owner'),'new')
            finally:state.close()


if __name__=='__main__':unittest.main()
