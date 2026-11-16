import unittest
from unittest.mock import patch
from scripts.transfer_probe import Probe,without_control_options,SAMPLE_BYTES

class ProbeTests(unittest.TestCase):
    def test_preserves_host_verification_but_removes_only_control_options(self):
        command=['ssh','-T','-o','StrictHostKeyChecking=yes','-o','ControlMaster=auto','-o','ControlPath=/tmp/old','root@fixture']
        self.assertEqual(without_control_options(command),['ssh','-T','-o','StrictHostKeyChecking=yes','root@fixture'])
    def test_no_install_or_oversized_command_can_reach_ssh(self):
        probe=Probe(['ssh','fixture'],'a'*40)
        for command in ['deploy '+'a'*40,'deploy-verified '+'a'*40+' '+'b'*64+' 100 1-1','site sha256:'+'c'*64,'transfer-info '+'a'*40+' '+'b'*64+' '+str(SAMPLE_BYTES+1)+' 1-1']:
            with patch('scripts.transfer_probe.subprocess.run') as run:
                with self.assertRaises(ValueError):probe.call(['ssh','fixture'],command)
                run.assert_not_called()
    def test_successful_probe_uses_only_status_and_bounded_staging(self):
        probe=Probe(['ssh','fixture'],'a'*40);calls=[]
        def call(ssh,command,data=None):
            calls.append((command,data))
            if command=='status':return {},.01
            if command.startswith('transfer-info '):return {'protocol':2,'bytes':0},.02
            self.assertTrue(command.startswith('upload-chunk '));self.assertEqual(len(data),SAMPLE_BYTES)
            return {'protocol':2,'bytes':len(data),'complete':True},.1
        probe.call=call
        with patch('scripts.transfer_probe.subprocess.run') as run:
            run.return_value.returncode=0
            result=probe.run()
        self.assertFalse(result['installation_requested'])
        self.assertEqual(len(calls),9)
        self.assertTrue(all(r['ok'] for r in result['results']))
        self.assertLessEqual(sum(len(data or b'') for _,data in calls),96*1024)
