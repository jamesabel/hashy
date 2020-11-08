import copy
import collections
import json
import typing

from hashy import get_string_md5, get_string_sha256, get_string_sha512


import json

from enum import Enum
from decimal import Decimal


def _convert_serializable_special_cases(o):

    """
    Convert an object to a type that is fairly generally serializable (e.g. json serializable).
    This only handles the cases that need converting.  The json module handles all the rest.
    For JSON, with json.dump or json.dumps with argument default=convert_serializable.
    Example:
    json.dumps(my_animal, indent=4, default=_convert_serializable)

    :param o: object to be converted to a type that is serializable
    :return: a serializable representation
    """

    if isinstance(o, Enum):
        serializable_representation = o.value
    elif isinstance(o, Decimal):
        # decimal.Decimal (e.g. in AWS DynamoDB), both integer and floating point
        if o % 1 == 0:
            # if representable with an integer, use an integer
            serializable_representation = int(o)
        else:
            # not representable with an integer so use a float
            serializable_representation = float(o)
    else:
        raise NotImplementedError(f"can not serialize {o} since type={type(o)}")
    return serializable_representation


def dls_sort(orig: (dict, list, set)) -> (dict, list):
    """
    Given a nested dictionary, set or list, return a sorted version.  Note that lists aren't sorted (they merely retain
    their original order).  Original data is unchanged.
    :param orig: original dict or list (may or may not be sorted)
    :return: sorted version of orig (note that we never return sets since they are unordered)
    """
    orig = copy.deepcopy(orig)
    if isinstance(orig, list):
        return [dls_sort(e) for e in orig]
    elif isinstance(orig, set):
        # have to sort sets to be consistent since they have no order
        return sorted(list(orig))
    elif isinstance(orig, dict) or isinstance(orig, collections.OrderedDict):
        sorted_dict = collections.OrderedDict()
        for k in sorted(orig):
            sorted_dict[k] = dls_sort(orig[k])
        return sorted_dict
    return orig


def _dls_hash(dl: (dict, list, set), string_hash_function: typing.Callable) -> str:
    """
    Given a possibly unordered nested dictionary, set or list, return a consistent hash of it.
    :param dl: dict or list
    :return: hash string corresponding to the dl input
    """
    separators = (",", ":")  # no whitespace
    sorted_dls_json = json.dumps(dls_sort(dl), default=_convert_serializable_special_cases, separators=separators)  # serialize the object (as json string)
    hash_result = string_hash_function(sorted_dls_json)  # do a hash on the (consistent and repeatable) string
    return hash_result


def get_dls_md5(dl: (dict, list, set)) -> str:
    """
    Given a possibly unordered nested dictionary, set or list, return a consistent hash of it.
    :param dl: dist or list
    :return: md5 hash string corresponding to the dl input
    """
    return _dls_hash(dl, get_string_md5)


def get_dls_sha256(dl: (dict, list, set)) -> str:
    """
    Given a possibly unordered nested dictionary, set or list, return a consistent hash of it.
    :param dl: dist or list
    :return: sha256 hash string corresponding to the dl input
    """
    return _dls_hash(dl, get_string_sha256)


def get_dls_sha512(dl: (dict, list, set)) -> str:
    """
    Given a possibly unordered nested dictionary, set or list, return a consistent hash of it.
    :param dl: dist or list
    :return: sha512 hash string corresponding to the dl input
    """
    return _dls_hash(dl, get_string_sha512)
