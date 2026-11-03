from autonews.pipeline.summarize import attest, normalize_hashtags, parse_number


def test_parse_number_formats():
    assert parse_number("1,000") == 1000
    assert parse_number("1 000") == 1000
    assert parse_number("3,5") == 3.5
    assert parse_number("3.5") == 3.5
    assert parse_number("2.500") == 2500
    assert parse_number("45,000") == 45000


def test_attest_accepts_reformatted_numbers():
    source = "The car has a 1,000 km range and costs $45,000. It charges 20-80% in 18 minutes."
    post = "Запас хода 1000 км, цена 45 000 долларов, зарядка 20-80% за 18 минут."
    report = attest(post, source)
    assert report["ok"], report


def test_attest_rejects_invented_number():
    source = "The car has a 1,000 km range."
    post = "Запас хода 1200 км."
    report = attest(post, source)
    assert not report["ok"]
    assert "1200" in report["missing"]


def test_attest_catches_small_unit_numbers():
    source = "The battery holds 83 kWh."
    post = "Батарея на 100 кВтч."
    report = attest(post, source)
    assert not report["ok"]


def test_attest_ignores_prose_number_words():
    source = "Two new trim levels were announced."
    post = "Объявлены две новые комплектации."
    assert attest(post, source)["ok"]


def test_hashtags_join_multiword():
    assert normalize_hashtags(["зарядная инфраструктура", "#BYD"]) == [
        "#зарядная_инфраструктура",
        "#byd",
    ]
