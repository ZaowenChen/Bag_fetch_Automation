from bagfetcher.core.parser import ParseError, bag_name_to_datetime, parse_paste


def test_parse_simple_block():
    block = "ssh gaussian@example.com -p 2222\nsecret"
    result = parse_paste(block)
    assert result.user == "gaussian"
    assert result.host == "example.com"
    assert result.port == 2222
    assert result.password == "secret"


def test_parse_defaults():
    block = "ssh user@host\n"
    result = parse_paste(block)
    assert result.port == 22
    assert result.password == ""


def test_parse_missing_ssh_line():
    try:
        parse_paste("not ssh")
    except ParseError as exc:
        assert "ssh" in str(exc)
    else:
        raise AssertionError("Expected ParseError")


def test_bag_name_to_datetime_parses_expected_format():
    dt = bag_name_to_datetime("GS_2023-11-06-15-45-32_001.bag")
    assert dt.year == 2023
    assert dt.minute == 45
