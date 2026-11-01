import asyncio
import unittest
from test_feiyu_bili import load

class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_tls_hostname(self):
        resolver=load('asr').ResolvedHost(['8.133.255.105'])
        rows=await resolver.resolve('api.siliconflow.cn',443)
        self.assertEqual(rows[0]['hostname'],'api.siliconflow.cn')
        self.assertEqual(rows[0]['host'],'8.133.255.105')
        with self.assertRaises(OSError):await resolver.resolve('localhost',443)
