import base64
import json
import unittest
from unittest.mock import AsyncMock, patch

from spark_assistant_tools import (ASSISTANT_NAMES, approved_staging_opportunity,
                                   assistant_live_config, execute_assistant_tool)
from spark_groq import GroqClient
from spark_web import execute_web_tool


class AssistantToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_inventory_never_claims_oauth_or_leaks_config(self):
        config = {'gmail': {'command': 'private-path', 'env': {'TOKEN': 'secret'},
                            'read_tools': ['google_account_status']}}
        with patch('spark_integrations.Integrations.catalog', return_value=config):
            result = await execute_assistant_tool('get_connection_status', {})
        self.assertEqual(result['services']['gmail']['state'], 'configured_unverified')
        self.assertEqual(result['services']['google-drive']['state'], 'not_configured')
        self.assertFalse(result['services']['gmail']['account_access_verified'])
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('private-path', json.dumps(result))

    async def test_invalid_configuration_is_not_reported_as_disconnected(self):
        from spark_productivity import WorkbenchError
        with patch('spark_integrations.Integrations.catalog', side_effect=WorkbenchError('secret')):
            result = await execute_assistant_tool('get_connection_status', {})
        self.assertFalse(result['ok'])
        self.assertNotIn('secret', json.dumps(result))

    async def test_inventory_cannot_accept_commands_or_account_selection(self):
        result = await execute_assistant_tool('get_connection_status', {'command': 'anything'})
        self.assertFalse(result['ok'])

    async def test_capabilities_help_explains_every_visible_control(self):
        result = await execute_assistant_tool('get_dashboard_help', {'page': 'Capabilities under Build'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['location'], 'Build > Capabilities')
        labels = {control['label'] for control in result['controls']}
        self.assertEqual(labels, {'Declared capabilities and gaps', 'Scan this checkout',
                                  'List roles', 'Refresh skill registry'})
        self.assertIn('read-only', result['safety'])
        self.assertIn('0', result['empty_state'])

    async def test_mission_page_alias_is_known_dashboard_help(self):
        result = await execute_assistant_tool('get_dashboard_help', {'page': 'mission page'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['location'], 'Workspace > Missions')

    async def test_repository_help_describes_safe_feature_adoption_workflow(self):
        result = await execute_assistant_tool('get_dashboard_help', {'page': 'Repositories'})
        self.assertTrue(result['ok'])
        labels = {control['label'] for control in result['controls']}
        self.assertIn('Analyze repository with model', labels)
        self.assertIn('Import license and dependency evidence', labels)
        self.assertIn('Stage this opportunity', labels)
        self.assertIn('explicit activation approval', result['safety'])

    async def test_workspace_tools_delegate_only_to_the_session_handler(self):
        handler = AsyncMock(return_value={'ok': True, 'screen': 'Repositories'})
        result = await execute_assistant_tool(
            'open_workspace_screen', {'screen': 'Repositories'}, handler)
        self.assertTrue(result['ok'])
        handler.assert_awaited_once_with(
            'open_workspace_screen', {'screen': 'Repositories'})
        unavailable = await execute_assistant_tool(
            'open_workspace_screen', {'screen': 'Repositories'})
        self.assertFalse(unavailable['ok'])

    async def test_staging_tool_requires_concrete_analysis_and_opportunity_fields(self):
        handler = AsyncMock(return_value={'ok': True, 'status': 'staged'})
        result = await execute_assistant_tool('stage_repository_opportunity', {
            'analysis_id': 'a' * 24, 'opportunity': 0,
        }, handler)
        self.assertEqual(result['status'], 'staged')
        handler.assert_awaited_once()

    async def test_groq_workspace_tool_carries_the_exact_user_utterance(self):
        client = GroqClient(key='test')
        handler = AsyncMock(return_value={'ok': True, 'screen': 'Repositories'})
        client.on_workspace_action = handler
        client.workspace_utterance = 'Walk me through it.'
        result = await client._web_call(
            'open_workspace_screen', '{"screen":"Repositories"}')
        self.assertTrue(result['ok'])
        handler.assert_awaited_once_with(
            'open_workspace_screen', {'screen': 'Repositories'},
            'Walk me through it.')

    def test_verbal_staging_approval_requires_an_exact_numbered_instruction(self):
        self.assertEqual(
            approved_staging_opportunity('I approve staging opportunity 2.'), 1)
        self.assertEqual(
            approved_staging_opportunity('Stage repository opportunity number 1'), 0)
        for vague in ('yes', 'approve it', 'go ahead', 'stage the opportunity',
                      'approve activation opportunity 1', 'stage opportunity 7'):
            self.assertIsNone(approved_staging_opportunity(vague), vague)

    def test_live_profiles_advertise_and_instruct_connection_checks(self):
        config = {'system_instruction': 'Original instruction.'}
        for profile in ('cinematic', 'cinematic_tools', 'cinematic_search', 'full'):
            result = assistant_live_config(config, profile)
            names = {tool['name'] for group in result['tools'] for tool in group['function_declarations']}
            self.assertEqual(names, ASSISTANT_NAMES)
            self.assertIn('configured adapter is not verified', result['system_instruction'])
            self.assertIn('get_dashboard_help', result['system_instruction'])
            self.assertIn('copy, port, learn from or adopt features', result['system_instruction'])
            self.assertIn('Do not refuse merely because Spark is local-first', result['system_instruction'])
            self.assertIn('open_workspace_screen first', result['system_instruction'])
            self.assertIn('approve staging opportunity 1', result['system_instruction'])
        self.assertNotIn('tools', config)
        self.assertIs(assistant_live_config(config, 'voice'), config)

    def test_gemini_function_schemas_avoid_unsupported_additional_properties(self):
        config = assistant_live_config({'system_instruction': 'Original instruction.'}, 'cinematic')
        declarations = [tool for group in config['tools'] for tool in group['function_declarations']]
        self.assertNotIn('additionalProperties', json.dumps(declarations))

    async def test_groq_answers_access_question_after_checking_actual_config(self):
        client = GroqClient(key='test')
        client._http = AsyncMock(side_effect=[
            {'choices': [{'message': {'content': None, 'tool_calls': [
                {'id': 'status-1', 'type': 'function', 'function': {
                    'name': 'get_connection_status', 'arguments': '{}'}}]}}]},
            {'choices': [{'message': {'content': 'Google Drive is not configured in this Spark launch.'}}]},
        ])
        with patch('spark_integrations.Integrations.catalog', return_value={}):
            answer = await client.chat('Do you have access to my Google Drive?', [])
        self.assertIn('not configured', answer)
        messages = client._http.call_args.kwargs['body']['messages']
        self.assertEqual(json.loads(messages[-1]['content'])['services']['google-drive']['state'], 'not_configured')

    async def test_groq_can_ground_capabilities_page_answer_in_dashboard_help(self):
        client = GroqClient(key='test')
        client._http = AsyncMock(side_effect=[
            {'choices': [{'message': {'content': None, 'tool_calls': [
                {'id': 'help-1', 'type': 'function', 'function': {
                    'name': 'get_dashboard_help', 'arguments': '{"page":"Capabilities"}'}}]}}]},
            {'choices': [{'message': {'content': 'Use the four read-only controls to inspect declarations, the checkout, roles, and project skills.'}}]},
        ])
        answer = await client.chat('How do I use Capabilities under Build?', [])
        self.assertIn('four read-only controls', answer)
        messages = client._http.call_args.kwargs['body']['messages']
        evidence = json.loads(messages[-1]['content'])
        self.assertEqual(evidence['location'], 'Build > Capabilities')

    async def test_groq_can_inspect_repo_before_answering_copy_feature_followup(self):
        client = GroqClient(key='test')
        client._http = AsyncMock(side_effect=[
            {'choices': [{'message': {'content': None, 'tool_calls': [
                {'id': 'repo-1', 'type': 'function', 'function': {
                    'name': 'inspect_public_github_repo',
                    'arguments': '{"repository":"open-jarvis/OpenJarvis"}'}}]}}]},
            {'choices': [{'message': {'content': 'Yes. Spark can adapt compatible Apache-2.0 features through a staged, reviewed upgrade.'}}]},
        ])
        evidence = {'ok': True, 'repository': 'open-jarvis/OpenJarvis',
                    'license': 'Apache-2.0', 'readme': 'Agents and local trace learning.'}
        history = [{'role': 'user', 'content': 'https://github.com/open-jarvis/OpenJarvis'},
                   {'role': 'assistant', 'content': 'OpenJarvis is a local-first personal AI framework.'}]
        with patch('spark_groq.execute_web_tool', AsyncMock(return_value=evidence)) as execute:
            answer = await client.chat('Can you copy any of its features to Spark?', history)
        self.assertTrue(answer.startswith('Yes.'))
        execute.assert_awaited_once_with('inspect_public_github_repo', {'repository': 'open-jarvis/OpenJarvis'})
        first_body = client._http.await_args_list[0].kwargs['body']
        self.assertIn('Do not refuse merely because Spark is local-first', first_body['messages'][0]['content'])
        self.assertIn('inspect_public_github_repo', {tool['function']['name'] for tool in first_body['tools']})

    async def test_public_repo_url_reads_metadata_root_and_readme_without_cli(self):
        responses = [('api', json.dumps({'full_name': 'open-jarvis/OpenJarvis', 'default_branch': 'main',
                                        'license': {'spdx_id': 'Apache-2.0'}})),
                     ('api', json.dumps([{'name': 'src', 'type': 'dir'}, {'name': 'README.md', 'type': 'file'}])),
                     ('api', json.dumps({'encoding': 'base64', 'content': base64.b64encode(b'# Project\nActual README.').decode()}))]
        with patch('spark_web.fetch_text', AsyncMock(side_effect=responses)) as fetch:
            result = await execute_web_tool('inspect_public_github_repo', {'repository': 'https://github.com/open-jarvis/OpenJarvis'})
        self.assertTrue(result['ok'])
        self.assertIn('Actual README.', result['readme'])
        self.assertEqual(result['root_files'][0]['name'], 'src')
        self.assertEqual(result['license'], 'Apache-2.0')
        self.assertEqual(fetch.await_args_list[0].args[0], 'https://api.github.com/repos/open-jarvis/OpenJarvis')

    async def test_public_repo_rejects_non_github_hosts_and_command_input(self):
        for value in ('https://evil.example/a/b', '--help', '../repo', 'owner/repo;command', 'https://github.com/a/b?token=secret'):
            with patch('spark_web.fetch_text', AsyncMock()) as fetch:
                result = await execute_web_tool('inspect_public_github_repo', {'repository': value})
            self.assertFalse(result['ok'])
            fetch.assert_not_awaited()

    async def test_missing_readme_preserves_verified_metadata(self):
        with patch('spark_web.fetch_text', AsyncMock(side_effect=[
            ('api', '{"full_name":"owner/repo"}'), OSError(), OSError()])):
            result = await execute_web_tool('inspect_public_github_repo', {'repository': 'owner/repo'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['unavailable'], ['/contents', '/readme'])
        self.assertNotIn('readme', result)
