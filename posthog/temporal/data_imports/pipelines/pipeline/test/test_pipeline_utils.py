import decimal
import uuid
from ipaddress import IPv4Address, IPv6Address

import pyarrow as pa
import pytest
from dateutil import parser

from posthog.temporal.data_imports.pipelines.pipeline.utils import (
    _get_max_decimal_type,
    normalize_table_column_names,
    table_from_py_list,
)


def test_table_from_py_list_uuid():
    uuid_ = uuid.uuid4()
    table = table_from_py_list([{"column": uuid_}])

    assert table.equals(pa.table({"column": [str(uuid_)]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_inconsistent_list():
    table = table_from_py_list([{"column": "hello"}, {"column": ["hi"]}])

    assert table.equals(pa.table({"column": ['["hello"]', '["hi"]']}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_inconsistent_other_types():
    table = table_from_py_list([{"column": "hello"}, {"column": 12}])

    assert table.equals(pa.table({"column": ['"hello"', "12"]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_inconsistent_types_with_none():
    table = table_from_py_list([{"column": None}, {"column": "hello"}, {"column": 12}, {"column": None}])

    assert table.equals(pa.table({"column": [None, '"hello"', "12", None]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_inconsistent_types_with_str_and_dict():
    table = table_from_py_list([{"column": "hello"}, {"column": {"field": 1}}])

    assert table.equals(pa.table({"column": ["hello", '{"field":1}']}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_with_lists():
    table = table_from_py_list([{"column": ["hello"]}, {"column": ["hi"]}])

    assert table.equals(pa.table({"column": ['["hello"]', '["hi"]']}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_with_nan():
    table = table_from_py_list([{"column": 1.0}, {"column": float("NaN")}])

    assert table.equals(pa.table({"column": [1.0, None]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.float64()),
            ]
        )
    )


def test_table_from_py_list_with_inf():
    table = table_from_py_list([{"column": 1.0}, {"column": float("Inf")}])

    assert table.equals(pa.table({"column": [1.0, None]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.float64()),
            ]
        )
    )


def test_table_from_py_list_with_negative_inf():
    table = table_from_py_list([{"column": 1.0}, {"column": -float("Inf")}])

    assert table.equals(pa.table({"column": [1.0, None]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.float64()),
            ]
        )
    )


def test_table_from_py_list_with_decimal_inf():
    table = table_from_py_list([{"column": decimal.Decimal(1)}, {"column": decimal.Decimal("Infinity")}])

    assert table.equals(pa.table({"column": [decimal.Decimal("1.0"), None]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.decimal128(2, 1)),
            ]
        )
    )


def test_table_from_py_list_with_negative_decimal_inf():
    table = table_from_py_list([{"column": decimal.Decimal(1)}, {"column": decimal.Decimal("-Infinity")}])

    assert table.equals(pa.table({"column": [decimal.Decimal("1.0"), None]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.decimal128(2, 1)),
            ]
        )
    )


def test_table_from_py_list_with_binary_column():
    table = table_from_py_list([{"column": 1.0, "some_bytes": b"hello"}])

    assert table.equals(pa.table({"column": [1.0]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.float64()),
            ]
        )
    )


def test_table_from_py_list_with_null_filled_binary_column():
    schema = pa.schema([pa.field("column", pa.string()), pa.field("some_bytes", pa.binary())])
    table = table_from_py_list([{"column": "hello", "some_bytes": None}], schema)

    assert table.equals(pa.table({"column": ["hello"]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_with_mixed_decimal_float_sizes():
    table = table_from_py_list([{"column": decimal.Decimal(1.0)}, {"column": 1000.01}])

    expected_schema = pa.schema({"column": pa.decimal128(6, 2)})
    assert table.equals(
        pa.table(
            {"column": pa.array([decimal.Decimal("1.0"), decimal.Decimal(str(1000.01))], type=pa.decimal128(6, 2))},
            schema=expected_schema,
        )
    )
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.decimal128(6, 2)),
            ]
        )
    )


def test_table_from_py_list_with_schema_and_mixed_decimals():
    schema = pa.schema({"column": pa.decimal128(1, 0)})
    table = table_from_py_list([{"column": 1}, {"column": 1.0}], schema)

    assert table.equals(pa.table({"column": [decimal.Decimal(1), decimal.Decimal(1)]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.decimal128(1, 0)),
            ]
        )
    )


def test_table_from_py_list_with_schema_and_str_timestamp():
    schema = pa.schema({"column": pa.timestamp("us")})
    table = table_from_py_list([{"column": "2024-01-01T00:00:00"}], schema)

    expected_schema = pa.schema([pa.field("column", pa.timestamp("us"), nullable=False)])
    assert table.equals(
        pa.table(
            {"column": pa.array([parser.parse("2024-01-01T00:00:00")], type=pa.timestamp("us"))}, schema=expected_schema
        )
    )
    assert table.schema.equals(expected_schema)


def test_table_from_py_list_with_schema_and_too_small_decimal_type():
    schema = pa.schema({"column": pa.decimal128(3, 3)})
    table = table_from_py_list([{"column": decimal.Decimal("1.001")}], schema)

    expected_schema = pa.schema([pa.field("column", pa.decimal128(38, 32))])
    assert table.equals(
        pa.table(
            {"column": pa.array([decimal.Decimal("1.00100000000000000000000000000000")], type=pa.decimal128(38, 32))}
        )
    )
    assert table.schema.equals(expected_schema)


@pytest.mark.parametrize(
    "decimals,expected",
    [
        ([decimal.Decimal("1")], pa.decimal128(2, 1)),
        ([decimal.Decimal("1.001112")], pa.decimal128(7, 6)),
        ([decimal.Decimal("0.001112")], pa.decimal128(6, 6)),
        ([decimal.Decimal("1.0100000")], pa.decimal128(8, 7)),
        # That is 1 followed by 37 zeroes to go over the pa.Decimal128 precision limit of 38.
        ([decimal.Decimal("10000000000000000000000000000000000000.1")], pa.decimal256(39, 1)),
    ],
)
def test_get_max_decimal_type_returns_correct_decimal_type(
    decimals: list[decimal.Decimal],
    expected: pa.Decimal128Type | pa.Decimal256Type,
):
    """Test whether expected PyArrow decimal type variant is returned."""
    result = _get_max_decimal_type(decimals)
    assert result == expected


def test_table_from_py_list_with_ipv4_address():
    table = table_from_py_list([{"column": IPv4Address("127.0.0.1")}])

    assert table.equals(pa.table({"column": ["127.0.0.1"]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_table_from_py_list_with_ipv6_address():
    table = table_from_py_list([{"column": IPv6Address("::1")}])

    assert table.equals(pa.table({"column": ["::1"]}))
    assert table.schema.equals(
        pa.schema(
            [
                ("column", pa.string()),
            ]
        )
    )


def test_normalize_table_column_names_prevents_collisions():
    # Create a table with columns that would collide when normalized
    table = pa.table({"foo___bar": ["value1"], "foo_bar": ["value2"], "another___field": ["value3"]})

    normalized_table = normalize_table_column_names(table)

    # First column gets normalized
    assert "foo_bar" in normalized_table.column_names
    # Second column that would collide gets underscore prefix
    assert "_foo_bar" in normalized_table.column_names
    # Non-colliding column gets normalized
    assert "another_field" in normalized_table.column_names

    # Verify the data is preserved
    assert normalized_table.column("foo_bar").to_pylist() == ["value2"]
    assert normalized_table.column("_foo_bar").to_pylist() == ["value1"]
    assert normalized_table.column("another_field").to_pylist() == ["value3"]


def test_table_from_py_list_with_rescaling_decimal_data_loss_error():
    # Very restrictive type, and the large_decimal value is too large for the schema
    schema = pa.schema({"column": pa.decimal128(5, 1)})
    large_decimal = decimal.Decimal("12345.6789")

    table = table_from_py_list([{"column": large_decimal}], schema)

    expected_schema = pa.schema([pa.field("column", pa.decimal128(38, 32))])
    assert table.equals(
        pa.table(
            {
                "column": pa.array(
                    [decimal.Decimal("12345.67890000000000000000000000000000")], type=pa.decimal128(38, 32)
                )
            }
        )
    )
    assert table.schema.equals(expected_schema)
