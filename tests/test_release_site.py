from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from scripts.extract_release_site import extract

class SiteTests(unittest.TestCase):
    def test_unapproved_image_or_commit_never_loads_docker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'manifest.json').write_text(json.dumps({'commit':'a'*40,'image_id':'sha256:'+'1'*64}))
            with patch('scripts.extract_release_site.subprocess.run') as docker:
                for image,commit in [('sha256:'+'2'*64,'a'*40),('sha256:'+'1'*64,'b'*40)]:
                    with self.assertRaises(ValueError):extract(root,root/'site',image,commit)
                docker.assert_not_called()
