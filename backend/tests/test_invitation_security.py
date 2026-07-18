import re

from app.core.invitations import (
    generate_invitation_code,
    hash_invitation_code,
    normalize_invitation_code,
)


def test_generated_invitation_code_has_human_readable_secure_format() -> None:
    code = generate_invitation_code()

    assert re.fullmatch(r"FK-[A-HJ-NP-Z2-9]{12}", code) is not None
    assert "0" not in code
    assert "1" not in code
    assert "I" not in code
    assert "O" not in code


def test_invitation_code_normalization_is_case_insensitive() -> None:
    assert normalize_invitation_code("  fk-abcd2345wxyz  ") == "FK-ABCD2345WXYZ"


def test_invitation_hash_is_stable_and_does_not_expose_code() -> None:
    raw_code = "FK-ABCD2345WXYZ"

    first_hash = hash_invitation_code(raw_code)
    second_hash = hash_invitation_code(raw_code.lower())

    assert first_hash == second_hash
    assert len(first_hash) == 64
    assert raw_code not in first_hash


def test_different_invitation_codes_have_different_hashes() -> None:
    assert hash_invitation_code("FK-ABCD2345WXYZ") != hash_invitation_code(
        "FK-ZYXW5432DCBA",
    )
