from ideadesk.bot import chunks


def test_long_text_is_split_into_messages_under_the_telegram_limit_without_losing_text():
    text = "\n".join(f"ligne {i} " + "x" * 200 for i in range(60))
    parts = chunks(text)
    assert len(parts) > 1 and all(len(p) <= 4096 for p in parts)
    assert "\n".join(parts) == text


def test_short_text_stays_one_message():
    assert chunks("court") == ["court"]
