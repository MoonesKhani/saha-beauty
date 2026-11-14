"""Repair transport formatting without exposing or mutating any real secret."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.prepare_ssh_key import KeyFormatError,normalize,prepare

class PrivateKeyFormattingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.original=self.root/'original'
        subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(self.original)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        self.value=self.original.read_text()
    def check(self,value):
        before=value;output=self.root/'prepared'
        changes=prepare(value,output)
        actual=subprocess.check_output(['ssh-keygen','-y','-P','','-f',str(output)])
        expected=subprocess.check_output(['ssh-keygen','-y','-P','','-f',str(self.original)])
        self.assertEqual(actual,expected);self.assertEqual(value,before)
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        return changes
    def test_valid_original_key(self):self.check(self.value)
    def test_crlf_mobile_copy(self):self.assertIn('CRLF line endings',self.check(self.value.replace('\n','\r\n')))
    def test_literal_backslash_n(self):self.assertIn('escaped newlines',self.check(self.value.replace('\n','\\n')))
    def test_json_wrapped_string(self):self.assertIn('quoted text',self.check(json.dumps(self.value)))
    def test_single_line_or_indented_body(self):
        lines=self.value.splitlines();flat=lines[0]+' '+''.join(lines[1:-1])+' '+lines[-1]
        self.check(flat)
    def test_base64_encoded_file(self):self.assertIn('base64 envelope',self.check(base64.b64encode(self.value.encode()).decode()))
    def test_missing_final_newline(self):self.check(self.value.rstrip())
    def test_public_key_is_not_accepted(self):
        with self.assertRaisesRegex(KeyFormatError,'PUBLIC key'):normalize(self.original.with_suffix('.pub').read_text())
    def test_encrypted_key_requires_appropriate_authentication(self):
        encrypted=self.root/'encrypted'
        subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','test-fixture-passphrase','-f',str(encrypted)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        with self.assertRaisesRegex(KeyFormatError,'passphrase-protected'):normalize(encrypted.read_text())
    def test_invalid_input_never_appears_in_error(self):
        value='PRIVATE_FIXTURE_MUST_NOT_APPEAR'
        with self.assertRaises(KeyFormatError) as error:normalize(value)
        self.assertNotIn(value,str(error.exception))
    def test_does_not_overwrite_an_existing_file(self):
        output=self.root/'prepared';output.write_text('preserve existing file')
        with self.assertRaises(FileExistsError):prepare(self.value,output)
        self.assertEqual(output.read_text(),'preserve existing file')

if __name__=='__main__':unittest.main()
