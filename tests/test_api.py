"""HTTP transport tests with real aiohttp and mocked HA adapter (not HA Core)."""
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name in ('homeassistant','homeassistant.components','homeassistant.components.http','homeassistant.core'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['homeassistant.components.http'].HomeAssistantView = object
sys.modules['homeassistant.core'].Context = object
from custom_components.fit_assistant.http import PairView, DashboardView, ActionView
from custom_components.fit_assistant.protocol import PairingPool, digest, matches


class PairingTests(unittest.TestCase):
    def test_expiration_and_one_use(self):
        now = [0]
        pool = PairingPool(lambda: now[0])
        code, token = pool.start()
        self.assertTrue(pool.waiting(token))
        self.assertFalse(pool.waiting('fake'))
        self.assertEqual(pool.consume(code), digest(token))
        self.assertIsNone(pool.consume(code))
        code, token = pool.start()
        now[0] = 601
        self.assertFalse(pool.waiting(token))
        self.assertIsNone(pool.consume(code))
    def test_rate_limit(self):
        pool = PairingPool(lambda: 0)
        for _ in range(6): self.assertIsNotNone(pool.start())
        self.assertIsNone(pool.start())
    def test_digest(self):
        token = 'a'*64
        self.assertTrue(matches(token, digest(token)))
        self.assertFalse(matches('b'*64, digest(token)))
        self.assertFalse(matches('💡', digest(token)))


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.first = SimpleNamespace(entry_id='first', title='First', options={'entities':['sensor.temp'], 'controls':['light.allowed']})
        self.second = SimpleNamespace(entry_id='second', title='Second', options={'entities':['sensor.other'], 'controls':['light.other'], 'token_hash':digest('b'*64)})
        self.entries = [self.first, self.second]
        self.hub = {'pool':PairingPool(), 'loaded':{'first','second'}, 'busy':set()}
        def state(name, val, unit=''): return SimpleNamespace(name=name, state=val, attributes={'unit_of_measurement':unit})
        self.states = {'sensor.temp':state('Temperature','24.1','°C'),'sensor.other':state('Other','22','°C'),'light.allowed':state('Light','off'),'light.other':state('Other light','on')}
        self.call = AsyncMock()
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain:self.entries), states=self.states, services=SimpleNamespace(async_call=self.call))
        app = web.Application()
        for cls, method in ((PairView,'POST'),(DashboardView,'GET'),(ActionView,'POST')):
            view = cls(hass,self.hub)
            app.router.add_route(method,view.url,getattr(view,method.lower()))
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.base = '/api/fit_assistant/v1/'
    async def asyncTearDown(self):
        await self.client.close()
    async def pair(self):
        res = await self.client.post(self.base+'pair',json={})
        self.assertEqual(res.status,200)
        data=await res.json()
        return data, {'X-Fit-Token':data['token']}
    async def test_pair_scope_action_and_revoke(self):
        data, headers = await self.pair()
        res=await self.client.get(self.base+'dashboard',headers=headers)
        self.assertEqual((await res.json())['status'],'pending')
        res=await self.client.post(self.base+'action',headers=headers,json={'entity':'light.allowed','action':'turn_on'})
        self.assertEqual(res.status,403)
        self.first.options['token_hash']=self.hub['pool'].consume(data['code'])
        res=await self.client.get(self.base+'dashboard',headers=headers)
        self.assertEqual(res.status,200)
        self.assertEqual([i['id'] for i in (await res.json())['items']],['sensor.temp','light.allowed'])
        for entity,action in [('light.other','turn_on'),('sensor.temp','turn_on'),('light.allowed','toggle'),('light.allowed','unlock')]:
            res=await self.client.post(self.base+'action',headers=headers,json={'entity':entity,'action':action})
            self.assertEqual(res.status,403)
        self.call.assert_not_called()
        res=await self.client.post(self.base+'action',headers=headers,json={'entity':'light.allowed','action':'turn_on'})
        self.assertEqual(res.status,200)
        self.call.assert_awaited_once()
        self.assertEqual(self.call.call_args.args,('light','turn_on',{'entity_id':'light.allowed'}))
        res=await self.client.get(self.base+'dashboard',headers={'X-Fit-Token':'b'*64})
        self.assertEqual([i['id'] for i in (await res.json())['items']],['sensor.other','light.other'])
        del self.first.options['token_hash']
        res=await self.client.get(self.base+'dashboard',headers=headers)
        self.assertEqual(res.status,403)
        res=await self.client.post(self.base+'action',headers=headers,json={'entity':'light.allowed','action':'turn_on'})
        self.assertEqual(res.status,403)
    async def test_no_auth_no_data_and_closed_pair(self):
        res=await self.client.get(self.base+'dashboard')
        self.assertEqual(res.status,403)
        self.first.options['token_hash']=digest('a'*64)
        res=await self.client.post(self.base+'pair')
        self.assertEqual(res.status,403)
    async def test_bad_request_unavailable_unload(self):
        self.first.options['token_hash']=digest('a'*64)
        headers={'X-Fit-Token':'a'*64}
        for body in ([], 'x'*1200, {'entity':['light.allowed'],'action':'turn_on'}):
            res=await self.client.post(self.base+'action',headers=headers,json=body)
            self.assertIn(res.status,(400,403))
        self.states['light.allowed'].state='unavailable'
        res=await self.client.post(self.base+'action',headers=headers,json={'entity':'light.allowed','action':'turn_on'})
        self.assertEqual(res.status,409)
        self.hub['loaded'].discard('first')
        res=await self.client.get(self.base+'dashboard',headers=headers)
        self.assertEqual(res.status,403)
        self.call.assert_not_called()

if __name__ == '__main__': unittest.main()
