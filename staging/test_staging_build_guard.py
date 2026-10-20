"""Pure artifact guard tests; no services, databases or production access."""
import tempfile
import unittest
from pathlib import Path
from start_phase7f import verify_staging_build


class StagingBuildGuardTests(unittest.TestCase):
    def test_only_isolated_api_and_correct_backoffice_base_are_publishable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'backoffice'/'dist';(root/'assets').mkdir(parents=True)
            script=root/'assets'/'index-test.js'
            index=root/'index.html'
            index.write_text('<script src="/backoffice/assets/index-test.js"></script>')
            for unsafe in ('https://api.apexpos.cloud/api','http://127.0.0.1:8000/api','',
                           'https://localhost:18770/api https://api.apexpos.cloud/api'):
                script.write_text(unsafe)
                with self.subTest(unsafe=unsafe),self.assertRaises(SystemExit):verify_staging_build(root)
            script.write_text('https://localhost:18770/api')
            verify_staging_build(root)
            index.write_text('<script src="/assets/index-test.js"></script>')
            with self.assertRaises(SystemExit):verify_staging_build(root)


if __name__=='__main__':unittest.main()
