from archiver.response import measurements_controller as rc


def create_clock_measurement(body):  # noqa: E501
    """Ingest a pScheduler clock result (skew/offset)

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_clock_measurement(body=body)


def create_latency_measurement(body):  # noqa: E501
    """Ingest pScheduler latency/owamp result (one/two-way delay, jitter, loss)

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_latency_measurement(body=body)


def create_mtu_measurement(body):  # noqa: E501
    """Ingest pScheduler MTU result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_mtu_measurement(body=body)

def create_rtt_measurement(body):  # noqa: E501
    """Ingest pScheduler RTT/ping result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_rtt_measurement(body=body)


def create_throughput_measurement(body):  # noqa: E501
    """Ingest pScheduler throughput (iperf3/nuttcp/ethr) result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_throughput_measurement(body=body)


def create_trace_measurement(body):  # noqa: E501
    """Ingest pScheduler Trace result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_trace_measurement(body=body)
