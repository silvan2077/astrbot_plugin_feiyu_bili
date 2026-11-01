import asyncio
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import AsyncMock
from test_feiyu_bili import load

class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=load('state').State(pathlib.Path(self.tmp.name)/'s.db')
        self.mod=load('engine')
        self.client=AsyncMock()
        self.client.discover.return_value=[{'bvid':'BV1xx411c7mD','title':'cat'}]
        self.client.content.return_value=({'bvid':'BV1xx411c7mD','title':'cat','duration':60},'description','intro')
        self.model=AsyncMock(side_effect=['0','a nice video'])
        self.asr=AsyncMock(return_value='recognized speech')
        self.send=AsyncMock(return_value=True)
        self.engine=self.mod.Engine(self.state,self.client,self.model,self.asr,self.send)
    async def asyncTearDown(self):self.state.close();self.tmp.cleanup()
    async def test_preview_never_sends_and_asr_cached(self):
        result=await self.engine.run('cat',preview=True)
        self.assertIn('ASR',self.model.await_args_list[1].args[0]);self.send.assert_not_awaited()
        self.asr.assert_awaited_once();self.assertEqual(self.state.cached('BV1xx411c7mD')[1],'recognized speech')
        self.assertFalse(self.state.seen('BV1xx411c7mD'))
    async def test_send_unknown_blocks_future(self):
        self.send.side_effect=TimeoutError()
        await self.engine.run('cat',now=1793498400)
        self.assertTrue(self.state.seen('BV1xx411c7mD'))
        self.assertEqual(self.state.allowed(1793505600),'unknown')
    async def test_long_video_skips_asr(self):
        self.client.content.return_value=({'bvid':'BV1xx411c7mD','title':'cat','duration':601},'description','intro')
        result=await self.engine.run('cat',preview=True)
        self.asr.assert_not_awaited();self.assertIn('简介',self.model.await_args_list[1].args[0])
    async def test_invalid_model_selection_sends_nothing(self):
        self.model.side_effect=['99']
        await self.engine.run('cat',preview=True)
        self.send.assert_not_awaited();self.asr.assert_not_awaited()
    async def test_asr_failure_is_labeled_description(self):
        self.asr.side_effect=RuntimeError('ASR unavailable')
        result=await self.engine.run('cat',preview=True)
        self.assertIn('仅标题和简介',self.model.await_args_list[1].args[0])
        self.assertIsNone(self.state.cached('BV1xx411c7mD'))
    async def test_updated_dsh_notes_override_local_cache(self):
        self.state.cache('BV1xx411c7mD','subtitle','OLD_CONTENT')
        self.client.content.return_value=({'bvid':'BV1xx411c7mD','title':'cat','duration':0},'dsh_notes','NEW_DSH_NOTES')
        result=await self.engine.run('cat',preview=True)
        self.assertIn('DSH观看笔记',self.model.await_args_list[1].args[0])
        self.assertIn('NEW_DSH_NOTES',self.model.await_args_list[1].args[0])
        self.assertNotIn('OLD_CONTENT',self.model.await_args_list[1].args[0])
        self.asr.assert_not_awaited()
    async def test_failed_send_not_successful(self):
        self.send.return_value=False
        await self.engine.run('cat',now=1793498400)
        self.assertFalse(self.state.seen('BV1xx411c7mD'))
        self.assertEqual(self.state.get('unanswered','0'),'0')
    async def test_no_reply_during_analysis_cannot_bypass_quiet_hours(self):
        await self.engine.run('cat',now=1793552400)
        self.send.assert_not_awaited()
    async def test_friend_share_omits_fixed_card_but_keeps_internal_facts(self):
        self.model.side_effect=['0','刷到只猫装作认真思考，盯着镜头半天不动，像极了等消息的你。']
        result=await self.engine.run('cat',now=1793498400)
        self.assertEqual(result,'分享成功')
        text=self.send.await_args.args[0]
        self.assertEqual(text,'刷到只猫装作认真思考，盯着镜头半天不动，像极了等消息的你。\nhttps://www.bilibili.com/video/BV1xx411c7mD')
        self.assertIn('ASR',self.state.get('last_content'))
    async def test_share_prompt_has_date_and_previous_wording(self):
        self.state.set('last_share','前一条已经用过的开头\nhttps://example.com')
        self.client.content.return_value=({'bvid':'BV1xx411c7mD','title':'cat','duration':0,'viewed_date':'2026-10-30'},'dsh_notes','note')
        await self.engine.run('cat',preview=True)
        prompt=self.model.await_args_list[1].args[0]
        self.assertIn('2026-10-30',prompt);self.assertIn('前一条已经用过的开头',prompt)

class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_third_party_edge_and_uses_official_backup(self):
        client=load('bili').Bili()
        client.get=AsyncMock(return_value={'dash':{'audio':[{'baseUrl':'https://edge.example.com:4483/a','backupUrl':['https://upos-sz-estgoss.bilivideo.com/a'],'bandwidth':100}]}})
        client.asset=AsyncMock(return_value=b'audio')
        self.assertEqual(await client.audio({'bvid':'BV1','cid':1}),b'audio')
        client.asset.assert_awaited_once_with('https://upos-sz-estgoss.bilivideo.com/a')
