import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_maintenance import MaintenanceError, digest
from spark_repo_upgrade import (PATCH_INSTRUCTION, patch_context, reconstruct_patches,
                                request_bytes, analysis_context)


class BoundedPatchTests(unittest.TestCase):
    def test_json_mode_has_explicit_json_instruction(self):
        self.assertIn('JSON', PATCH_INSTRUCTION)

    def setUp(self):
        self.text = 'def calculate(x):\n    return x\n\n# owner note\n'
        self.source = {'path': 'backend/calculate.py', 'sha256': digest(self.text.encode()),
                       'content': self.text}
        self.sources = [self.source]
        self.opportunity = {'title': 'calculate', 'rationale': 'Double results',
                            'evidence': [self.source['path']],
                            'spark_paths': [self.source['path']], 'verification': 'calculate(3) == 6'}
        self.report = {'goal': 'Improve calculate', 'sources': self.sources}
        self.context = patch_context(self.report, self.opportunity, self.sources)
        self.response = {'patches': [{'path': self.source['path'], 'sha256': self.source['sha256'],
                                     'edits': [{'old': 'return x', 'new': 'return x * 2'}]}]}

    def test_reconstructs_without_touching_unrelated_text(self):
        changes = reconstruct_patches(self.response, self.sources, self.context)
        self.assertEqual(changes[0]['content'], 'def calculate(x):\n    return x * 2\n\n# owner note\n')
        self.assertEqual(changes[0]['sha256'], self.source['sha256'])

    def test_rejects_invalid_scope_hash_anchors_overlap_and_budget(self):
        cases = []
        for field, value in [('path', '../outside.py'), ('sha256', '0' * 64),
                             ('edits', []), ('edits', [{'old': '', 'new': 'x'}]),
                             ('edits', [{'old': 'missing', 'new': 'x'}]),
                             ('edits', [{'old': 'return x', 'new': 'return x'}]),
                             ('edits', [{'old': 'return x', 'new': 'x' * 8000}]),
                             ('edits', [{'old': 'return x', 'new': 'y'}, {'old': 'x', 'new': 'z'}]),
                             ('edits', [{'old': 'return x', 'new': 'y', 'extra': True}])]:
            response = copy.deepcopy(self.response)
            response['patches'][0][field] = value
            cases.append(response)
        duplicate = copy.deepcopy(self.response)
        duplicate['patches'] *= 2
        cases += [duplicate, {'patches': []}, {'changes': []}, None]
        for response in cases:
            with self.subTest(response=str(response)[:100]), self.assertRaises(MaintenanceError):
                reconstruct_patches(response, self.sources, self.context)

    def test_rejects_anchor_outside_excerpt(self):
        self.context['spark_sources'][0]['content'] = '# unrelated excerpt'
        with self.assertRaisesRegex(MaintenanceError, 'anchor'):
            reconstruct_patches(self.response, self.sources, self.context)

    def test_rejects_ambiguous_and_overlapping_original_spans(self):
        self.response['patches'][0]['edits'] = [{'old': 'x', 'new': 'y'}]
        with self.assertRaisesRegex(MaintenanceError, 'anchor'):
            reconstruct_patches(self.response, self.sources, self.context)
        self.response['patches'][0]['edits'] = [
            {'old': 'return x', 'new': 'y'}, {'old': '    return x', 'new': 'z'}]
        with self.assertRaisesRegex(MaintenanceError, 'overlap'):
            reconstruct_patches(self.response, self.sources, self.context)

    def test_edits_use_original_offsets_even_if_replacement_contains_another_anchor(self):
        self.response['patches'][0]['edits'] = [
            {'old': 'return x', 'new': '# owner note'}, {'old': '# owner note', 'new': '# retained'}]
        result = reconstruct_patches(self.response, self.sources, self.context)[0]['content']
        self.assertEqual(result, 'def calculate(x):\n    # owner note\n\n# retained\n')

    def test_large_unicode_sources_fit_serialized_budget_without_duplicate_source(self):
        sources = [{**self.source, 'path': f'backend/module{i}.py',
                    'content': '# 界"\\\n' * 4000 + self.text} for i in range(4)]
        report = {**self.report, 'sources': sources}
        opportunity = {**self.opportunity, 'evidence': [s['path'] for s in sources]}
        context = patch_context(report, opportunity, sources)
        self.assertLessEqual(request_bytes(PATCH_INSTRUCTION, context), 9000)
        self.assertTrue(all('content' not in s for s in context['reference_sources']))
        self.assertTrue(any('def calculate' in s['content'] for s in context['spark_sources']))

    def test_analysis_selects_goal_function_at_end_of_large_source(self):
        text = '# unrelated\n' * 3000 + self.text
        evidence = {'sources': [{**self.source, 'content': text}], 'inventory': [], 'limitations': []}
        context = analysis_context(evidence, 'Fix calculate(x)', [self.source['path']])
        self.assertIn('def calculate', context['sources'][0]['content'])

    def test_overlapping_occurrences_are_also_ambiguous(self):
        self.source['content'] = 'aaa'
        self.context['spark_sources'][0]['content'] = 'aaa'
        self.response['patches'][0]['edits'] = [{'old': 'aa', 'new': 'b'}]
        with self.assertRaisesRegex(MaintenanceError, 'anchor'):
            reconstruct_patches(self.response, self.sources, self.context)

    def test_reconstruction_preserves_unedited_crlf_and_unicode(self):
        self.source['content'] = '# 界\r\ndef calculate(x):\r\n    return x\r\n'
        self.context['spark_sources'][0]['content'] = self.source['content']
        result = reconstruct_patches(self.response, self.sources, self.context)[0]['content']
        self.assertEqual(result, '# 界\r\ndef calculate(x):\r\n    return x * 2\r\n')


if __name__ == '__main__':
    unittest.main()
