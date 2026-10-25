"""Exercise shell installation against a disposable home, without SSH or Slurm."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hendrix.shell import REMOTE_INSTALL


@unittest.skipUnless(os.environ.get('HENDRIX_REMOTE_ZOXIDE'), 'requires packaged static zoxide')
class ShellSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home), TERM='xterm-ghostty',
                        XDG_CONFIG_HOME=str(self.home / '.config'),
                        XDG_DATA_HOME=str(self.home / '.local/share'),
                        HISTFILE='/dev/null')
        self.project = self.home / "projects/ATDL-MeanFlow project 'quoted'"
        self.project.mkdir(parents=True)
        self.original = '# Existing user setup\nexport KEEP_EXISTING=preserved\n\n'
        (self.home / '.bashrc').write_text(self.original)
        (self.home / '.bash_profile').write_text('. "$HOME/.bashrc"\n')
        binary = Path(os.environ['HENDRIX_REMOTE_ZOXIDE']).read_bytes()
        self.payload = dict(
            zoxide=base64.b64encode(binary).decode('ascii'),
            sha256=hashlib.sha256(binary).hexdigest(),
            terminfo=subprocess.check_output(['infocmp', '-x', 'xterm-ghostty'], text=True),
            shell=(Path(__file__).parents[1] / 'scripts/hendrix/shell.bash').read_text(),
            project=str(self.project))

    def install(self):
        return subprocess.run([sys.executable, '-c', REMOTE_INSTALL],
                              input=json.dumps(self.payload), text=True,
                              capture_output=True, env=self.env, check=True)

    def test_repeat_install_preserves_startup_and_original_backups(self):
        self.install()
        installed = (self.home / '.bashrc').read_bytes()
        backups = sorted((self.home / '.config/hendrix/backups').iterdir())
        self.assertEqual(len(backups), 2)
        saved = next(path for path in backups if path.name.startswith('.bashrc.'))
        self.assertEqual(saved.read_text(), self.original)
        self.assertTrue(installed.startswith(self.original.encode()))
        self.install()
        self.assertEqual((self.home / '.bashrc').read_bytes(), installed)
        self.assertEqual(sorted((self.home / '.config/hendrix/backups').iterdir()), backups)
        self.assertEqual(installed.count(b'# BEGIN hendrix shell-setup'), 1)
        subprocess.run(['infocmp', '-A', str(self.home / '.terminfo'), 'xterm-ghostty'],
                       capture_output=True, env=self.env, check=True)

    def test_fuzzy_cd_and_normal_navigation_with_quoted_directory(self):
        self.install()
        script = 'cd mean; pwd; cd ..; pwd; cd - >/dev/null; pwd; printf "%s\\n" "$KEEP_EXISTING"'
        result = subprocess.run(['bash', '--noprofile', '--rcfile', str(self.home / '.bashrc'),
                                 '-ic', script], capture_output=True, text=True, env=self.env,
                                cwd=self.home, check=True)
        self.assertEqual(result.stdout.splitlines(), [
            str(self.project), str(self.project.parent), str(self.project), 'preserved'])
        self.assertNotIn('invalid keymap', result.stderr)

    def test_noninteractive_shell_leaves_cd_and_prompt_unchanged(self):
        self.install()
        script = 'PS1=original; source "$HOME/.bashrc"; test "$PS1" = original; test "$(type -t cd)" = builtin'
        subprocess.run(['bash', '--noprofile', '--norc', '-c', script],
                       env=self.env, check=True, capture_output=True)

    def test_corrupt_binary_does_not_modify_startup_files(self):
        self.payload['sha256'] = '0' * 64
        with self.assertRaises(subprocess.CalledProcessError):
            self.install()
        self.assertEqual((self.home / '.bashrc').read_text(), self.original)
        self.assertFalse((self.home / '.config/hendrix/shell.bash').exists())


if __name__ == '__main__':
    unittest.main()
