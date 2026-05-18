from outfitmatch.body.shape_rules import classify_body_shape


def test_hourglass():
    assert classify_body_shape(shoulder=40.0, waist=28.0, hip=40.0) == "hourglass"


def test_pear():
    assert classify_body_shape(shoulder=34.0, waist=30.0, hip=42.0) == "pear"


def test_inverted_triangle():
    assert classify_body_shape(shoulder=44.0, waist=32.0, hip=34.0) == "inverted_triangle"


def test_rectangle():
    assert classify_body_shape(shoulder=38.0, waist=36.0, hip=38.0) == "rectangle"


def test_apple():
    assert classify_body_shape(shoulder=38.0, waist=42.0, hip=37.0) == "apple"
