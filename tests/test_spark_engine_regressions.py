import asyncio
from pathlib import Path
from unittest.mock import patch, Mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import spark_autonomous_engine as engine


def test_audio_constructor_and_voice_write_boundary():
    import spark
    with patch.object(spark, 'client', None), patch.object(spark, 'KasaAgent'), patch.object(spark, 'PrinterAgent'), patch('project_manager.ProjectManager'):
        loop = spark.AudioLoop()
    assert callable(loop.on_inspect_self)
    with patch.object(loop, 'on_write_upgrade_patch') as writer:
        answer = asyncio.run(loop.answer_mcp_tool('write_upgrade_patch', {'patch_spec': '{}'}))
    assert 'Upgrade Studio' in answer
    writer.assert_not_called()


def test_readonly_command_runs_and_mutating_command_rejected():
    result = engine.execute_development_command('git status --short')
    assert result['returncode'] == 0 and result['error'] is None
    with patch.object(engine.subprocess, 'run') as runner:
        assert engine.execute_development_command('git reset --hard')['error']
        assert engine.execute_development_command('python -m pytest ../outside.py')['error']
    runner.assert_not_called()


def test_real_test_evidence_required_and_filter_is_separate_argument():
    assert not engine.verify_upgrade('change', {'failed': False})['passed']
    assert engine.stage_upgrade('change', {'failed': False})['stage'] == 'fails tests'
    assert engine.verify_upgrade('change', {'failed': False, 'returncode': 0})['passed']
    with patch.object(engine.subprocess, 'run', return_value=Mock(returncode=1, stdout='failed', stderr='')) as runner:
        result = engine.run_upgrade_tests('audio or sync')
    assert result['failed']
    assert runner.call_args.args[0][-2:] == ['-k', 'audio or sync']
    assert runner.call_args.kwargs['cwd'] == str(engine.PROJECT_ROOT)


def test_patch_validates_all_targets_before_writing(tmp_path):
    (tmp_path/'backend').mkdir()
    source = tmp_path/'backend'/'safe.py'
    source.write_text('original')
    with patch.object(engine, 'PROJECT_ROOT', tmp_path):
        _, error = engine.write_upgrade_patch({'files': {'backend/safe.py': 'changed', 'backend-other/bad.py': 'bad'}})
        assert error
        assert engine.read_source_file('.env')[1]
        assert engine.rollback_upgrade()[1]
    assert source.read_text() == 'original'


def test_verification_handler_uses_actual_tests():
    import spark
    loop = object.__new__(spark.AudioLoop)
    failed = {'failed': True, 'returncode': 1, 'stdout': 'failed', 'stderr': ''}
    with patch.object(spark, 'run_upgrade_tests', return_value=failed) as runner:
        answer = asyncio.run(loop.on_verify_upgrade('change'))
    import json
    assert not json.loads(answer)['passed']
    runner.assert_called_once()
