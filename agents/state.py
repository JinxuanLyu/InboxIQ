from typing import TypedDict


class EmailState(TypedDict):
    email: str
    classification: dict
    extracted: dict
    research: str
    replies: list
