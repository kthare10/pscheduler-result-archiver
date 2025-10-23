import unittest

from flask import json

from archiver.openapi_server.models.measurement import Measurement  # noqa: E501
from archiver.openapi_server.models.status401_unauthorized import Status401Unauthorized  # noqa: E501
from archiver.openapi_server.models.status403_forbidden import Status403Forbidden  # noqa: E501
from archiver.openapi_server.models.status404_not_found import Status404NotFound  # noqa: E501
from archiver.openapi_server.test import BaseTestCase


class TestArchivesController(BaseTestCase):
    """ArchivesController integration test stubs"""

    def test_get_measurement(self):
        """Test case for get_measurement

        Fetch a previously ingested run
        """
        headers = { 
            'Accept': 'application/json',
            'x_request_id': 'x_request_id_example',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/ps/archives/{run_id}'.format(run_id='run_id_example'),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
