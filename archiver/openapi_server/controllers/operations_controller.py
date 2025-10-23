from archiver.response import operations_controller as rc


def get_health():  # noqa: E501
    """Health/Liveness

     # noqa: E501


    :rtype: Union[GetHealth200Response, Tuple[GetHealth200Response, int], Tuple[GetHealth200Response, int, Dict[str, str]]
    """
    return rc.get_health()


def get_schema():  # noqa: E501
    """Metric catalog / minimal schema

     # noqa: E501


    :rtype: Union[GetSchema200Response, Tuple[GetSchema200Response, int], Tuple[GetSchema200Response, int, Dict[str, str]]
    """
    return rc.get_schema()
