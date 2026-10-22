from askdb.auth import hash_password, verify_password


def test_password_is_hashed_not_stored_as_plaintext():
    hashed = hash_password("correct horse battery")
    assert "correct horse battery" not in hashed
    assert hashed.startswith("$argon2")


def test_correct_password_verifies():
    hashed = hash_password("correct horse battery")
    assert verify_password(hashed, "correct horse battery") is True


def test_wrong_password_fails():
    hashed = hash_password("correct horse battery")
    assert verify_password(hashed, "wrong password") is False


def test_malformed_hash_fails_instead_of_raising():
    assert verify_password("not-a-hash", "anything") is False
