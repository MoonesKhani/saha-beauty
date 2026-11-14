"""Run the real update preflight against isolated Git repositories, never a server."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/server-update.sh'

class ServerUpdatePreflightTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'existing project'
        self.repo.mkdir()
        self.real_git = shutil.which('git')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Preflight Test')
        self.git('config', 'user.email', 'preflight@example.invalid')
        (self.repo / 'compose.yaml').write_text('services: {}\n')
        (self.repo / 'tracked.txt').write_text('original\n')
        (self.repo / '.gitignore').write_text('.env\nvar/\nbackups/\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Fixture')
        # Stop at the next read-only guard if the clean check succeeds.
        self.git('remote', 'add', 'origin', 'https://example.invalid/not-the-project.git')
        (self.repo / '.env').write_text('PRIVATE_FIXTURE=keep-existing-settings\n')
        (self.repo / 'var').mkdir()
        (self.repo / 'var/reservations.db').write_bytes(b'existing-reservations-fixture')
        (self.repo / 'var/photo.webp').write_bytes(b'existing-upload-fixture')
        self.before = {p:p.read_bytes() for p in self.repo.rglob('*') if p.is_file() and '.git' not in p.parts}
        fake_bin = self.root / 'bin'
        fake_bin.mkdir()
        docker = fake_bin / 'docker'
        docker.write_text('#!/bin/sh\nif [ "$*" = "compose version" ]; then exit 0; fi\necho "Unexpected Docker operation" >&2\nexit 99\n')
        docker.chmod(0o755)
        git = fake_bin / 'git'
        git.write_text('#!/bin/sh\nif [ "${SAHA_TEST_STATUS_FAILURE:-0}" = 1 ] && [ "${1:-}" = status ]; then echo "Git status fixture failure" >&2; exit 128; fi\nexec "$SAHA_TEST_REAL_GIT" "$@"\n')
        git.chmod(0o755)
        self.environment = {**os.environ, 'PATH':str(fake_bin)+os.pathsep+os.environ['PATH'], 'SAHA_TEST_REAL_GIT':self.real_git}

    def git(self, *args):
        return subprocess.run([self.real_git, *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def run_update(self, **environment):
        result = subprocess.run(['bash', str(SCRIPT), str(self.repo)], env={**self.environment, **environment}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0) # Every fixture stops before deployment.
        self.assertNotIn('Unexpected Docker operation', result.stderr)
        self.assertFalse((self.repo / 'backups').exists())
        for file in ['.env','var/reservations.db','var/photo.webp']:
            path = self.repo / file
            self.assertEqual(path.read_bytes(), self.before[path])
        self.assertNotIn('keep-existing-settings', result.stdout+result.stderr)
        return result.stderr

    def test_clean_repository_passes_change_guard(self):
        self.assertEqual(self.git('status', '--short'), '')
        self.git('diff', '--quiet')
        self.git('diff', '--cached', '--quiet')
        output = self.run_update()
        self.assertIn('origin با مخزن تأییدشده', output)
        self.assertNotIn('تغییر ذخیره‌نشده', output)

    def test_unstaged_change_stops_before_deployment(self):
        (self.repo / 'tracked.txt').write_text('owner edit\n')
        self.assertIn('تغییر ذخیره‌نشده', self.run_update())
        self.assertEqual((self.repo / 'tracked.txt').read_text(), 'owner edit\n')

    def test_staged_change_stops_before_deployment(self):
        (self.repo / 'tracked.txt').write_text('staged owner edit\n')
        self.git('add', 'tracked.txt')
        self.assertIn('تغییر ذخیره‌نشده', self.run_update())
        self.assertIn('M  tracked.txt', self.git('status', '--short'))

    def test_untracked_files_are_preserved(self):
        file = self.repo / 'owner-notes.txt'
        file.write_text('keep these notes\n')
        self.assertIn('origin با مخزن تأییدشده', self.run_update())
        self.assertEqual(file.read_text(), 'keep these notes\n')

    def test_git_error_is_not_reported_as_a_dirty_repository(self):
        output = self.run_update(SAHA_TEST_STATUS_FAILURE='1')
        self.assertIn('بررسی وضعیت مخزن ناموفق بود', output)
        self.assertNotIn('تغییر ذخیره‌نشده', output)

if __name__ == '__main__':
    unittest.main()
