from archiver.response import archives_controller as rc


def get_measurement(run_id, x_request_id=None):  # noqa: E501
    """Fetch a previously ingested run

     # noqa: E501

    :param run_id: 
    :type run_id: str
    :param x_request_id: Optional request correlation id
    :type x_request_id: str

    :rtype: Union[Measurement, Tuple[Measurement, int], Tuple[Measurement, int, Dict[str, str]]
    """
    return rc.get_measurement(run_id=run_id, x_request_id=x_request_id)
