from names import save_name


def test_valid_name():
    assert save_name("Ada")["saved"] == "Ada"
