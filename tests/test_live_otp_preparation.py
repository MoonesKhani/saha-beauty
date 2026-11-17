import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import deploy_release as release

spec=importlib.util.spec_from_file_location('scripts.live_otp',Path(__file__).parents[1]/'scripts/prepare-live-otp.py')
live=importlib.util.module_from_spec(spec);spec.loader.exec_module(live)

class PreparationTests(unittest.TestCase):
    def test_only_tls_domain_root_changes_and_api_is_preserved(self):
        original='server { listen 80; server_name sahabeauty.ir; return 301 https://$host$request_uri; }\nserver { listen 443 ssl; server_name sahabeauty.ir www.sahabeauty.ir; root /var/www/saha; location /api/ { proxy_pass http://127.0.0.1:8000; } }'
        tls=[b for b in live.server_blocks(original) if b['tls']][0]
        changed=live.route_site(original,tls)
        self.assertIn('root /var/lib/saha-release/current;',changed)
        self.assertIn('location /api/ { proxy_pass http://127.0.0.1:8000; }',changed)
        self.assertIn('return 301 https://$host$request_uri;',changed)
    def test_quoted_comment_braces_and_full_site_proxy(self):
        text='server { # ignored }\n listen 443 ssl; server_name "sahabeauty.ir"; location / { proxy_set_header Host $host; proxy_pass http://127.0.0.1:8000; } }'
        self.assertEqual(live.route_site(text,live.server_blocks(text)[0]),text)
    def test_api_proxy_alone_does_not_prove_frontend_routing(self):
        text='server { listen 443 ssl; server_name sahabeauty.ir; location /api/ { proxy_pass http://127.0.0.1:8000; } }'
        with self.assertRaises(release.DeploymentError):live.route_site(text,live.server_blocks(text)[0])
    def test_nested_root_and_ambiguous_vhosts_stop(self):
        text='server { listen 443 ssl; server_name sahabeauty.ir; root /var/www; location /assets/ { root /elsewhere; } }'
        with self.assertRaises(release.DeploymentError):live.route_site(text,live.server_blocks(text)[0])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'saha';path.write_text(text+text)
            with self.assertRaises(release.DeploymentError):live.nginx_target('# configuration file '+str(path)+':\n')
    def test_existing_keys_retained_no_notifications_or_new_key(self):
        environment={'MELIPAYAMAK_API_KEY':'fixture-key-1234567890','SAHA_OTP_SECRET':'existing-fixture-secret-'*3,'DATABASE_URL':'private-fixture'}
        result=live.live_environment(environment)
        for key in environment:self.assertEqual(result[key],environment[key])
        self.assertEqual(result['SAHA_OTP_ENABLED'],'1');self.assertEqual(result['SAHA_SMS_LIVE_ENABLED'],'1')
        self.assertEqual(result['SAHA_SMS_NOTIFICATIONS_ENABLED'],'0')
        self.assertEqual(result['SAHA_BOOKING_REQUIRE_OTP'],'1')
        with self.assertRaises(release.DeploymentError) as error:live.live_environment({})
        self.assertNotIn('private-fixture',str(error.exception))

    def test_public_static_site_and_identity_follow_rollback_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp)/'project';(project/'.deploy').mkdir(parents=True)
            (project/'.deploy/public-release.enabled').touch()
            engine=release.ComposeEngine.__new__(release.ComposeEngine);engine.project=project
            engine.compose=lambda:['compose']
            current={}
            def run(args,label,**kwargs):
                if label=='find current app':return 'container'
                if label=='inspect current image':return json.dumps([{'Id':current['image_id'],'Config':{'Labels':{'org.opencontainers.image.revision':current['commit']}}}])
                if label=='extract verified public site':
                    target=Path(args[-1]);(target/'index.html').write_text(current['commit']);return ''
                raise AssertionError(label)
            engine.run=run;engine.inspect=lambda _:{'Id':'container','Image':current['image_id']}
            public=Path(tmp)/'public'
            previous_umask=os.umask(0o077)
            self.addCleanup(os.umask,previous_umask)
            with patch.object(release,'PUBLIC_RELEASE_ROOT',public):
                for digit in ['a','b','a']:
                    current={'image_id':'sha256:'+digit*64,'commit':digit*40}
                    engine.publish_identity(current)
                    self.assertEqual(json.loads((public/'current/release.json').read_text()),current)
                    self.assertEqual((public/'current/index.html').read_text(),current['commit'])
                    self.assertEqual((public/'current/release.json').stat().st_mode&0o777,0o644)
                    for directory in [public,public/'sites',(public/'current').resolve()]:
                        self.assertEqual(directory.stat().st_mode&0o777,0o755)
                    # A subsequent invocation must repair a retained private directory too.
                    (public/'sites').chmod(0o700)
                    (public/'current').resolve().chmod(0o700)
                with self.assertRaises(release.DeploymentError):
                    engine.publish_identity({'image_id':'sha256:'+'f'*64,'commit':'f'*40})
                self.assertEqual((public/'current/index.html').read_text(),'a'*40)

if __name__=='__main__':unittest.main()
