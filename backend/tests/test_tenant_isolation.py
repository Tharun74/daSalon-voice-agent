from app.tools import (
    tool_get_services,
    tool_get_staff,
    tool_get_offers,
    tool_get_hours,
    tool_check_availability,
    tool_book_appointment,
    tool_cancel_appointment,
)
from app.rag import get_vector_store

def test_tool_services_isolation():
    glow_srv = tool_get_services("glow-studio")
    serenity_srv = tool_get_services("serenity-spa")
    gentleman_srv = tool_get_services("gentlemans-cut")

    glow_names = [s["name"] for s in glow_srv["services"]]
    serenity_names = [s["name"] for s in serenity_srv["services"]]
    gentleman_names = [s["name"] for s in gentleman_srv["services"]]

    assert "Signature Haircut & Blowdry" in glow_names
    assert "Signature Haircut & Blowdry" not in serenity_names
    assert "Signature Haircut & Blowdry" not in gentleman_names

    assert "Couples Spa Ritual Package" in serenity_names
    assert "Couples Spa Ritual Package" not in glow_names
    assert "Couples Spa Ritual Package" not in gentleman_names

    assert "Royal Hot Towel Shave" in gentleman_names
    assert "Royal Hot Towel Shave" not in glow_names
    assert "Royal Hot Towel Shave" not in serenity_names


def test_tool_staff_isolation():
    glow_staff = [s["name"] for s in tool_get_staff("glow-studio")["staff"]]
    serenity_staff = [s["name"] for s in tool_get_staff("serenity-spa")["staff"]]
    gentleman_staff = [s["name"] for s in tool_get_staff("gentlemans-cut")["staff"]]

    assert "Ananya Sharma" in glow_staff
    assert "Ananya Sharma" not in serenity_staff
    assert "Ananya Sharma" not in gentleman_staff

    assert "Meera Nair" in serenity_staff
    assert "Meera Nair" not in glow_staff
    assert "Meera Nair" not in gentleman_staff

    assert "Vikram Singh" in gentleman_staff
    assert "Vikram Singh" not in glow_staff
    assert "Vikram Singh" not in serenity_staff


def test_tool_offers_isolation():
    glow_offers = [o["title"] for o in tool_get_offers("glow-studio")["offers"]]
    serenity_offers = [o["title"] for o in tool_get_offers("serenity-spa")["offers"]]
    gentleman_offers = [o["title"] for o in tool_get_offers("gentlemans-cut")["offers"]]

    assert "Weekday Glow Deal" in glow_offers
    assert "Weekday Glow Deal" not in serenity_offers

    assert "Midweek Serenity Escape" in serenity_offers
    assert "Midweek Serenity Escape" not in glow_offers

    assert "Father & Son Duo" in gentleman_offers
    assert "Father & Son Duo" not in glow_offers


def test_rag_vector_store_isolation():
    store = get_vector_store()
    # Add chunk for glow-studio
    store.add_chunks(
        salon_id="glow-studio",
        doc_id="glow-doc-test",
        filename="glow.txt",
        chunks=["Glow Studio secret cancellation policy: 4 hours notice required."],
    )

    # Query glow-studio
    glow_res = store.query(salon_id="glow-studio", query_text="cancellation policy")
    assert len(glow_res) > 0
    assert "4 hours" in glow_res[0]["content"]

    # Query serenity-spa (must return NOTHING from glow)
    serenity_res = store.query(salon_id="serenity-spa", query_text="cancellation policy")
    for r in serenity_res:
        assert "Glow Studio" not in r["content"]

    # Query gentlemans-cut
    gentleman_res = store.query(salon_id="gentlemans-cut", query_text="cancellation policy")
    for r in gentleman_res:
        assert "Glow Studio" not in r["content"]

    # Clean up
    store.delete_by_doc_id(salon_id="glow-studio", doc_id="glow-doc-test")
