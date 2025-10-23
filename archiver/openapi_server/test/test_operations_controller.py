import unittest

from flask import json

from archiver.openapi_server.models.get_health200_response import GetHealth200Response  # noqa: E501
from archiver.openapi_server.models.get_schema200_response import GetSchema200Response  # noqa: E501
from archiver.openapi_server.models.status401_unauthorized import Status401Unauthorized  # noqa: E501
from archiver.openapi_server.test import BaseTestCase


class TestOperationsController(BaseTestCase):
    """OperationsController integration test stubs"""

    def test_get_health(self):
        """Test case for get_health

        Health/Liveness
        """
        headers = { 
            'Accept': 'application/json',
            'apiKeyAuth': 'special-key',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/ps/health',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_schema(self):
        """Test case for get_schema

        Metric catalog / minimal schema
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/ps/schema',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
