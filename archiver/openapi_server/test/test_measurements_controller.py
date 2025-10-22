import unittest

from flask import json

from archiver.openapi_server.models.measurement_request import MeasurementRequest  # noqa: E501
from archiver.openapi_server.models.status200_ok_no_content import Status200OkNoContent  # noqa: E501
from archiver.openapi_server.models.status400_bad_request import Status400BadRequest  # noqa: E501
from archiver.openapi_server.models.status401_unauthorized import Status401Unauthorized  # noqa: E501
from archiver.openapi_server.models.status403_forbidden import Status403Forbidden  # noqa: E501
from archiver.openapi_server.models.status404_not_found import Status404NotFound  # noqa: E501
from archiver.openapi_server.models.status500_internal_server_error import Status500InternalServerError  # noqa: E501
from archiver.openapi_server.test import BaseTestCase


class TestMeasurementsController(BaseTestCase):
    """MeasurementsController integration test stubs"""

    def test_create_clock_measurement(self):
        """Test case for create_clock_measurement

        Ingest a pScheduler clock result (skew/offset)
        """
        measurement_request = {"run_id":"run_id","dst":{"ip":"ip","name":"name"},"src":{"ip":"ip","name":"name"},"raw":{"key":""},"ts":"2000-01-23T04:56:07.000+00:00","direction":"forward"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/measurements/clock',
            method='POST',
            headers=headers,
            data=json.dumps(measurement_request),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_latency_measurement(self):
        """Test case for create_latency_measurement

        Ingest pScheduler latency/owamp result (one/two-way delay, jitter, loss)
        """
        measurement_request = {"run_id":"run_id","dst":{"ip":"ip","name":"name"},"src":{"ip":"ip","name":"name"},"raw":{"key":""},"ts":"2000-01-23T04:56:07.000+00:00","direction":"forward"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/measurements/latency',
            method='POST',
            headers=headers,
            data=json.dumps(measurement_request),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_mtu_measurement(self):
        """Test case for create_mtu_measurement

        Ingest pScheduler MTU result
        """
        measurement_request = {"run_id":"run_id","dst":{"ip":"ip","name":"name"},"src":{"ip":"ip","name":"name"},"raw":{"key":""},"ts":"2000-01-23T04:56:07.000+00:00","direction":"forward"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/measurements/mtu',
            method='POST',
            headers=headers,
            data=json.dumps(measurement_request),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_rtt_measurement(self):
        """Test case for create_rtt_measurement

        Ingest pScheduler RTT/ping result
        """
        measurement_request = {"run_id":"run_id","dst":{"ip":"ip","name":"name"},"src":{"ip":"ip","name":"name"},"raw":{"key":""},"ts":"2000-01-23T04:56:07.000+00:00","direction":"forward"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/measurements/rtt',
            method='POST',
            headers=headers,
            data=json.dumps(measurement_request),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_throughput_measurement(self):
        """Test case for create_throughput_measurement

        Ingest pScheduler throughput (iperf3/nuttcp/ethr) result
        """
        measurement_request = {"run_id":"run_id","dst":{"ip":"ip","name":"name"},"src":{"ip":"ip","name":"name"},"raw":{"key":""},"ts":"2000-01-23T04:56:07.000+00:00","direction":"forward"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/measurements/throughput',
            method='POST',
            headers=headers,
            data=json.dumps(measurement_request),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_trace_measurement(self):
        """Test case for create_trace_measurement

        Ingest pScheduler Trace result
        """
        measurement_request = {"run_id":"run_id","dst":{"ip":"ip","name":"name"},"src":{"ip":"ip","name":"name"},"raw":{"key":""},"ts":"2000-01-23T04:56:07.000+00:00","direction":"forward"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/measurements/trace',
            method='POST',
            headers=headers,
            data=json.dumps(measurement_request),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
