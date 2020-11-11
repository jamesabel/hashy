from collections import OrderedDict
from enum import Enum
import json
from pprint import pprint

from hashy import dls_sort, get_dls_md5, get_dls_sha256, get_dls_sha512, json_dumps


def test_dl_sort():

    in_dict = OrderedDict()
    in_dict["z"] = "y"
    # list order is maintained, but the items in the list should be ordered
    in_dict["series"] = [{"x": "p", "w": "q"}, {"b": "c", "a": "d"}]
    in_dict["a"] = "t"  # this will be first
    in_dict["x"] = "w"

    sorted_dict = dls_sort(in_dict)
    separators = (",", ":")  # no whitespace
    sorted_as_json_string = json.dumps(sorted_dict, separators=separators)
    expected_string = '{"a":"t","series":[{"w":"q","x":"p"},{"a":"d","b":"c"}],"x":"w","z":"y"}'
    assert sorted_as_json_string == expected_string
    dict_hash_256 = get_dls_sha256(in_dict)
    assert dict_hash_256 == "5e377db305768c39637196a96db33b223e0b4775293d8d4101efc2c79424b612"

    dict_hash_md5 = get_dls_md5(in_dict)
    assert dict_hash_md5 == "11e9afb8526e9a91e732800af970ec6c"

    dict_hash_512 = get_dls_sha512(in_dict)
    assert dict_hash_512 == "a010a6ff0601b3e4cd33ffff6004718b5145302c24960904778bfedc4228521345c8936322ff267e49f321bdc404b3720492ace7434a4669d1896018fa55e285"


def test_enum():

    class MyEnum(Enum):
        a = 1
        b = 2
    enum_example = {"b": MyEnum.b, "a": MyEnum.a}

    assert json_dumps(dls_sort(enum_example)) == '{"a":"a","b":"b"}'  # sorted and test that we're using the .name (not the .value) of the Enum

    assert get_dls_md5(enum_example) == "e3f5105b86f8bca747510d72bcaa131b"


def test_set_sort():
    x = {"a", "c", "b"}  # set
    y = ["a", "b", "c"]
    md5 = "c29a5747d698b2f95cdfd5ed6502f19d"
    assert dls_sort(x) == dls_sort(y)
    assert get_dls_md5(x) == md5
    assert get_dls_md5(y) == md5
