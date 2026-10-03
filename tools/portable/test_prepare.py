import unittest

from prepare import NOTICE, prepare


class PrepareTests(unittest.TestCase):
    def test_preserves_new_upstream_behavior_and_resources(self):
        body = '# New upstream workflow\n\nRead [rubric](references/rubric.md).\nRun the actual app.\n'
        original = '---\nname: New Workflow\ndescription: "Run the new workflow."\nmode: true\n---\n\n' + body
        adapted = prepare(original, 'new-workflow')
        self.assertEqual(adapted.split(NOTICE, 1)[1], body)
        self.assertIn('name: new-workflow\n', adapted)
        self.assertIn('mode: true\n', adapted)

    def test_repeated_update_does_not_duplicate_notice(self):
        original = '---\nname: example\ndescription: Example\n---\n\n# Example\n'
        once = prepare(original, 'example')
        self.assertEqual(prepare(once, 'example'), once)

    def test_upstream_added_step_survives_another_update(self):
        original = '---\nname: example\ndescription: Example\n---\n\n# Example\n'
        updated = prepare(original, 'example') + '\nVerify the new side effect.\n'
        self.assertEqual(prepare(updated, 'example'), updated)

    def test_malformed_upstream_manifest_fails(self):
        with self.assertRaises(ValueError):
            prepare('# Missing manifest\n', 'example')

    def test_migrates_plugin_only_reference_without_changing_body(self):
        body = '# Example\nVerify the actual result.\n'
        legacy = ('On Claude Code or Codex, first read [the runtime adaptation]'
                  '(../../compatibility.md). Apply its substitutions to this skill.\n\n')
        original = '---\nname: example\ndescription: Example\n---\n\n' + legacy + body
        adapted = prepare(original, 'example')
        self.assertNotIn('../../compatibility.md', adapted)
        self.assertEqual(adapted.split(NOTICE, 1)[1], body)


if __name__ == '__main__':
    unittest.main()
