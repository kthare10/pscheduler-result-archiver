from typing import List

from archiver.common.globals import get_globals


def info_from_bearerAuth(token):
    """
    Check and retrieve authentication information from custom bearer token.
    Returned value will be passed in 'token_info' parameter of your operation function, if there is one.
    'sub' or 'uid' will be set in 'user' parameter of your operation function, if there is one.

    :param token Token provided by Authorization header
    :type token: str
    :return: Decoded token information or None if token is invalid
    :rtype: dict | None
    """
    if token is None or token != get_globals().config.runtime.bearer_token:
        return None
    return {'uid': 'user_id'}


def info_from_apiKeyAuth(api_key, required_scopes):
    """
    Check and retrieve authentication information from api_key.
    Returned value will be passed in 'token_info' parameter of your operation function, if there is one.
    'sub' or 'uid' will be set in 'user' parameter of your operation function, if there is one.

    :param api_key API key provided by Authorization header
    :type api_key: str
    :param required_scopes Always None. Used for other authentication method
    :type required_scopes: None
    :return: Information attached to provided api_key or None if api_key is invalid or does not allow access to called API
    :rtype: dict | None
    """
    if api_key is None or api_key != get_globals().config.runtime.bearer_token:
        return None
    return {'uid': 'user_id'}

