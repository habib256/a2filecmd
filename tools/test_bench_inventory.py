"""Every bench belongs to the qualification runner, and the runner to the CI.

Before bench/all.py, the release replay was the `bench` job of ci.yml: it
played twenty-five benches out of ninety-three, and the seven benches written
for the 0.8.9 formats were not among them. Nothing said so. This is the same
guard the host tests already have by hand -- every tools/test_*.py is a line
of `make test` -- written down for the benches instead:

- each bench/*.py is a step of bench/all.py, a name of bench/plugins.py, or a
  declared helper (bench/all.py HELPERS says what it is instead);
- each step names a bench that exists, and a fixture the runner knows;
- the `bench` job of ci.yml runs the groups of the table, all of them.

    python3 -m unittest tools.test_bench_inventory -v
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import all as runner                            # bench/all.py, the table
import plugins as overlay_benches               # bench/plugins.py, the overlay list

CI = (ROOT / '.github/workflows/ci.yml').read_text()


class Inventory(unittest.TestCase):
    def test_every_bench_is_played(self):
        played = {s.bench for s in runner.STEPS} | set(overlay_benches.BENCHES) | set(runner.HELPERS)
        forgotten = sorted(p.stem for p in (ROOT / 'bench').glob('*.py') if p.stem not in played)
        self.assertEqual(forgotten, [], 'benches in no step of bench/all.py: add them, or say in '
                                        'HELPERS what they are instead')

    def test_every_step_names_a_bench(self):
        for step in runner.STEPS:
            with self.subTest(step=step.name):
                self.assertTrue((ROOT / 'bench' / (step.bench + '.py')).exists())
            for tag in step.needs:
                self.assertIn(tag, runner.FIXTURES, step.name)

    def test_step_names_are_unique(self):
        names = [s.name for s in runner.STEPS]
        self.assertEqual(sorted(names), sorted(set(names)))

    def test_the_overlay_list_is_real(self):
        for name in overlay_benches.BENCHES:
            self.assertTrue((ROOT / 'bench' / (name + '.py')).exists(), name)

    def test_helpers_serve_a_bench(self):
        """A helper is imported by a bench, or builds a fixture: never idle."""
        imported = set()
        for path in (ROOT / 'bench').glob('*.py'):
            imported |= set(re.findall(r'^\s*(?:from|import)\s+(\w+)', path.read_text(), re.M))
        builders = {Path(part).stem for fixture in runner.FIXTURES.values()
                    for part in (fixture.build or []) if part.endswith('.py')}
        for name in runner.HELPERS:
            if name in ('all', 'plugins'):      # the runners themselves
                continue
            self.assertTrue(name in imported or name in builders,
                            '%s is neither imported by a bench nor a fixture builder: '
                            'it is probably a bench, so give it a step' % name)

    def test_ci_plays_every_group(self):
        """The bench job of ci.yml is the runner, group by group."""
        job = CI.split('  bench:', 1)[1]
        self.assertTrue('bench/all.py' in job, 'the CI bench job must call bench/all.py')
        for group in runner.GROUPS:
            self.assertTrue(re.search(r'--group[^\n]*\b%s\b' % re.escape(group), job),
                            'group %s is in no CI step' % group)

    def test_ports_are_read_from_the_bench(self):
        """The runner never writes a port down: it reads them to avoid collisions."""
        self.assertIn(6601, runner.ports('smoke'))
        self.assertIn(6849, runner.ports('fixit'))


if __name__ == '__main__':
    unittest.main()
