import pytest

from askdb.sqlguard import UnsafeSQL, validate


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT 1;",
        "select customer_id, company_name from customers where industry = 'Retail'",
        "WITH x AS (SELECT 1 AS a) SELECT a FROM x",
        "WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c WHERE n < 3) SELECT n FROM c",
        "SELECT 1 UNION SELECT 2",
    ],
)
def test_accepts_a_single_select(sql):
    validate(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "DROP TABLE customers",
        "INSERT INTO customers (customer_id) VALUES (1)",
        "UPDATE customers SET industry = 'x'",
        "PRAGMA query_only = OFF",
        "SELECT 1; DELETE FROM customers",
        "WITH x AS (SELECT 1) DELETE FROM customers",
        "WITH x AS (SELECT 1) INSERT INTO customers (customer_id) SELECT * FROM x",
        "",
        "   ;  ",
        "SELECT (",
    ],
)
def test_rejects_writes_and_multiple_statements(sql):
    with pytest.raises(UnsafeSQL):
        validate(sql)


def test_rejection_message_is_safe_to_show():
    with pytest.raises(UnsafeSQL, match="exactly one statement"):
        validate("SELECT 1; SELECT 2")
