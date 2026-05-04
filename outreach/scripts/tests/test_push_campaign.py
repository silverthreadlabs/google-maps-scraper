"""Tests for scripts/push_campaign — campaign upsert via API."""
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.push_campaign import (
    _resolve_api_key,
    _vertical_from_config,
    upsert_campaign,
    main,
)


class TestResolveApiKey(unittest.TestCase):
    def test_cli_key_takes_precedence(self):
        with patch.dict('os.environ', {'OUTREACH_API_KEY': 'env_key'}):
            self.assertEqual(_resolve_api_key('cli_key'), 'cli_key')

    def test_falls_back_to_env(self):
        with patch.dict('os.environ', {'OUTREACH_API_KEY': 'env_key'}):
            self.assertEqual(_resolve_api_key(None), 'env_key')

    def test_exits_when_missing(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                _resolve_api_key(None)
            self.assertEqual(ctx.exception.code, 2)


class TestVerticalFromConfig(unittest.TestCase):
    def test_explicit_vertical_attr(self):
        cfg = ModuleType('cfg')
        cfg.VERTICAL = 'cosmetic surgery'
        self.assertEqual(_vertical_from_config(cfg), 'cosmetic surgery')

    def test_falls_back_to_docstring(self):
        cfg = ModuleType('cfg')
        cfg.__doc__ = 'Dental Sunbelt campaign.\nMore details.'
        self.assertEqual(_vertical_from_config(cfg), 'Dental Sunbelt campaign')

    def test_empty_when_no_info(self):
        cfg = ModuleType('cfg')
        cfg.__doc__ = None
        self.assertEqual(_vertical_from_config(cfg), '')


class TestUpsertCampaign(unittest.TestCase):
    @patch('scripts.push_campaign.urllib.request.urlopen')
    def test_success(self, mock_urlopen):
        response_data = {'success': True, 'data': {'id': 'uuid-1', 'slug': 'test'}}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = upsert_campaign(
            base_url='http://localhost:3001',
            api_key='test-key-1234567890abcdef1234567890ab',
            slug='dental_sunbelt',
            name='Dental Sunbelt',
            metro='austin',
            vertical='dental',
        )
        self.assertEqual(result['data']['id'], 'uuid-1')

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        self.assertEqual(body['slug'], 'dental_sunbelt')
        self.assertEqual(req.get_header('Authorization'), 'Bearer test-key-1234567890abcdef1234567890ab')


class TestMainCLI(unittest.TestCase):
    @patch('scripts.push_campaign.upsert_campaign')
    @patch('scripts.push_campaign.load_pipeline_config')
    @patch('scripts.push_campaign._resolve_api_key')
    def test_derives_slug_from_pipeline_name(self, mock_key, mock_cfg, mock_upsert):
        mock_key.return_value = 'key123456789012345678901234567890'
        cfg = ModuleType('cfg')
        cfg.METROS = ['dallas']
        cfg.__doc__ = 'Cosmetic Surgeons Dallas.'
        mock_cfg.return_value = cfg
        mock_upsert.return_value = {'data': {'id': 'uuid-1'}}

        code = main(['cosmetic_surgeons_dallas', '--api-key', 'key123456789012345678901234567890'])
        self.assertEqual(code, 0)
        call_kwargs = mock_upsert.call_args[1]
        self.assertEqual(call_kwargs['slug'], 'cosmetic_surgeons_dallas')
        self.assertEqual(call_kwargs['metro'], 'dallas')


if __name__ == '__main__':
    unittest.main()
