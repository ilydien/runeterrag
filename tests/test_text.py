from src.common.text import (
    extract_card_links,
    normalize_name,
    singularize,
    strip_markup,
    text_status,
)


def test_strip_markup_removes_all_tags():
    raw = (
        "Deal 2 to a <link=keyword.Stun><sprite name=Stunned>"
        "<style=Keyword>Stunned</style></link> unit."
    )
    assert strip_markup(raw) == "Deal 2 to a Stunned unit."


def test_strip_markup_handles_br_and_crlf():
    assert strip_markup("Round Start: Draw 1.\r\n<br>Then pass.") == (
        "Round Start: Draw 1. Then pass."
    )


def test_text_status():
    assert text_status("<style=Variable></style>", "") == "placeholder"
    assert text_status("", "") == "attributes_only"
    assert text_status("Deal 1.", "Deal 1.") == "native"


def test_normalize_name():
    assert normalize_name("Yasuo's Steel Tempest") == "yasuo steel tempest"
    assert normalize_name("Kai'Sa") == "kai sa"
    assert normalize_name("Piltover & Zaun") == "piltover zaun"


def test_singularize():
    assert singularize("Living Shadows") == "living shadow"
    assert singularize("Mistwraiths") == "mistwraith"
    assert singularize("Lucky Finds") == "lucky find"


def test_extract_card_links():
    raw = "Create a <link=card.level1><style=AssociatedCard>Yasuo</style></link> in your deck."
    assert extract_card_links(raw) == [("level1", "Yasuo")]
