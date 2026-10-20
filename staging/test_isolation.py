"""Fail-closed configuration checks; no database/network access."""
import copy
import json
from unittest.mock import patch
import unittest
import phase7f_runtime as runtime

class IsolationTests(unittest.TestCase):
    def data(self):
        return {'environment':'phase7f-staging','database':'apexretail_phase7f_acceptance',
            'source':'/tmp/apexpos-phase7f','api_environment':{'APP_ENV':'staging'},
            'database_url':'postgresql+asyncpg://apex_user:synthetic@/apexretail_phase7f_acceptance?host=/tmp/apexretail-phase7f-runtime/socket&port=55437'}

    def validate(self, data):
        with patch.object(runtime.Path,'read_text',return_value=json.dumps(data)):
            return runtime.settings()

    def test_accepts_only_expected_local_instance(self):
        self.assertEqual(self.validate(self.data())['database'],'apexretail_phase7f_acceptance')

    def test_rejects_production_or_other_connection(self):
        for url in [
            'postgresql+asyncpg://apex_user:x@localhost/apexretail_pos',
            'postgresql+asyncpg://apex_user:x@/apexretail_pos?host=/tmp/apexretail-phase7f-runtime/socket&port=55437',
            'postgresql+asyncpg://apex_user:x@/apexretail_phase7f_acceptance?host=/var/run/postgresql&port=5432',
            'postgresql+asyncpg://postgres:x@/apexretail_phase7f_acceptance?host=/tmp/apexretail-phase7f-runtime/socket&port=55437',
            self.data()['database_url']+'&service=production',
        ]:
            with self.subTest(url=url):
                data=self.data(); data['database_url']=url
                with self.assertRaises(RuntimeError): self.validate(data)

    def test_rejects_production_environment(self):
        data=copy.deepcopy(self.data());data['api_environment']['APP_ENV']='production'
        with self.assertRaises(RuntimeError): self.validate(data)

if __name__ == '__main__': unittest.main()
