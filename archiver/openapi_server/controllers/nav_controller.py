from archiver.response import nav_controller as rc


def create_nav_measurement(body):  # noqa: E501
    """Ingest a batch of vessel navigation data points

     # noqa: E501

    :param body:
    :type body: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    return rc.create_nav_measurement(body=body)


def get_nav_data(start=None, end=None, vessel_id=None, limit=1000):  # noqa: E501
    """Retrieve vessel navigation data by time range

     # noqa: E501

    :param start: Start of time range (ISO 8601)
    :param end: End of time range (ISO 8601)
    :param vessel_id: Vessel identifier
    :param limit: Maximum number of rows

    :rtype: NavDataResponse
    """
    return rc.get_nav_data(start=start, end=end, vessel_id=vessel_id, limit=limit)
